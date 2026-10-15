"""Optional audio refinement adapted from Adudeguyman/ComfyUI-H3-AudioRefine.

MIT attribution: LICENSES/ComfyUI-H3-AudioRefine.txt.
"""

import torch
import json
import math
import comfy.nested_tensor
import comfy.sample
import comfy.samplers
import comfy.utils
import latent_preview


def av_streams(latent):
    samples = latent.get("samples")
    if not getattr(samples, "is_nested", False) or len(samples.tensors) != 2:
        raise ValueError("SKEBA Audio Refine requires a sampled H3 video/audio latent.")
    video, audio = samples.unbind()
    if video.ndim != 5 or audio.ndim != 4 or video.shape[1] != 24 or audio.shape[1] != 32:
        raise ValueError("SKEBA Audio Refine requires H3 video and audio streams.")
    return video, audio


class SkebaH3FinishInpaintLatent:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "finish"
    RETURN_TYPES = ("LATENT", "STRING")
    RETURN_NAMES = ("latent", "status")
    DESCRIPTION = ("After the H3 inpaint sampler has completed, remove its old generation mask "
                   "before passing the finished AV latent to an upscaler. Video and audio samples "
                   "are unchanged. Do not place this before the inpaint sampler.")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"completed_latent": ("LATENT",)}}

    def finish(self, completed_latent):
        av_streams(completed_latent)
        output = completed_latent.copy()
        had_mask = output.pop("noise_mask", None) is not None
        return (output, "Finished H3 inpaint latent: removed old noise mask."
                if had_mask else "Finished H3 latent: no noise mask was present.")


def refinement_mask(latent, boundary_latent=None, *, edit_start_seconds=None,
                    edit_end_seconds=None, replace_locked_audio=False):
    video, audio = av_streams(latent)
    audio_mask = torch.ones_like(audio, dtype=torch.float32)
    for source in (latent, boundary_latent):
        if source is None:
            continue
        if source is latent and replace_locked_audio:
            continue
        mask = source.get("noise_mask")
        if mask is None:
            if source is boundary_latent:
                raise ValueError("SKEBA Audio Refine: boundary_latent has no noise mask. Connect the AV Connector latent before sampling.")
            continue
        if not getattr(mask, "is_nested", False) or len(mask.tensors) != 2:
            raise ValueError("SKEBA Audio Refine: expected a packed H3 boundary mask.")
        _, source_audio = av_streams(source)
        if source_audio.shape != audio.shape:
            raise ValueError("SKEBA Audio Refine: boundary audio length differs; use the same pass's untrimmed latent.")
        incoming = mask.tensors[1].to(device=audio.device, dtype=torch.float32)
        if incoming.ndim != audio.ndim or any(m not in (1, n) for m, n in zip(incoming.shape, audio.shape)):
            raise ValueError("SKEBA Audio Refine: boundary mask does not match the sampled audio.")
        if not torch.isfinite(incoming).all() or (incoming < 0).any() or (incoming > 1).any():
            raise ValueError("SKEBA Audio Refine: boundary mask must contain finite values from zero to one.")
        audio_mask = torch.minimum(audio_mask, incoming)
    if edit_start_seconds is not None or edit_end_seconds is not None:
        if edit_start_seconds is None or edit_end_seconds is None:
            raise ValueError("SKEBA Audio Inpaint: connect both edit start and end times.")
        start, end = float(edit_start_seconds), float(edit_end_seconds)
        duration = audio.shape[-1] / 40.0
        if not 0 <= start < end <= duration:
            raise ValueError(f"SKEBA Audio Inpaint: range must satisfy 0 <= start < end <= {duration:g} seconds.")
        first = max(0, min(audio.shape[-1], round(start * 40)))
        last = max(0, min(audio.shape[-1], round(end * 40)))
        if last <= first:
            raise ValueError("SKEBA Audio Inpaint: range is shorter than one 40 Hz audio-latent frame.")
        audio_mask[..., :first] = 0
        audio_mask[..., last:] = 0
    video_mask = torch.zeros((video.shape[0], 1, *video.shape[2:]), device=video.device, dtype=torch.float32)
    return comfy.nested_tensor.NestedTensor((video_mask, audio_mask))


class SkebaH3AudioRefine:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "refine"
    RETURN_TYPES = ("LATENT",)
    RETURN_NAMES = ("latent",)
    DESCRIPTION = "Optional extra H3 audio sampling with video frozen and existing audio boundaries protected. Place before AV decode and trimming. Off returns the original latent."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent": ("LATENT",),
            "enabled": ("BOOLEAN", {"default": False}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "control_after_generate": True}),
            "steps": ("INT", {"default": 4, "min": 1, "max": 100}),
            "audio_denoise": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.01}),
            "cfg": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 100.0, "step": 0.1}),
            "sampler_name": (comfy.samplers.KSampler.SAMPLERS, {"default": "euler"}),
            "scheduler": (comfy.samplers.KSampler.SCHEDULERS, {"default": "simple"}),
        }, "optional": {
            "model": ("MODEL", {"lazy": True, "tooltip": "Required when enabled. Prefer the H3 model before the Turbo LoRA."}),
            "positive": ("CONDITIONING", {"lazy": True}),
            "negative": ("CONDITIONING", {"lazy": True}),
            "boundary_latent": ("LATENT", {"lazy": True, "tooltip": "Optional: same pass AV Connector latent before sampling, if the sampled latent lost its mask. Never connect a trimmed or different-length latent."}),
            "noise": ("NOISE", {"lazy": True, "tooltip": "Connect RandomNoise's NOISE output here, not to seed. Overrides the numeric seed and uses this source to generate refinement noise."}),
        }}

    def check_lazy_status(self, enabled, audio_denoise, **kwargs):
        if not enabled or audio_denoise == 0:
            return []
        return [name for name in ("model", "positive", "negative", "boundary_latent", "noise")
                if name in kwargs and kwargs[name] is None]

    def refine(self, latent, enabled=False, seed=0, steps=4, audio_denoise=0.3,
               cfg=1.0, sampler_name="euler", scheduler="simple", model=None,
               positive=None, negative=None, boundary_latent=None, noise=None,
               edit_start_seconds=None, edit_end_seconds=None, replace_locked_audio=False):
        if not enabled or audio_denoise == 0:
            return (latent,)
        if model is None or positive is None or negative is None:
            raise ValueError("SKEBA Audio Refine: connect model, positive and negative when enabled.")
        mask = refinement_mask(latent, boundary_latent,
                               edit_start_seconds=edit_start_seconds,
                               edit_end_seconds=edit_end_seconds,
                               replace_locked_audio=replace_locked_audio)
        if not torch.any(mask.tensors[1]):
            return (latent,)
        video, audio = av_streams(latent)
        if noise is None:
            noise_samples = comfy.sample.prepare_noise(latent["samples"], seed, latent.get("batch_index"))
        else:
            seed = noise.seed
            noise_samples = noise.generate_noise(latent)
        samples = comfy.sample.sample(
            model, noise_samples, steps, cfg, sampler_name, scheduler, positive, negative,
            latent["samples"], denoise=audio_denoise, noise_mask=mask,
            callback=latent_preview.prepare_callback(model, steps),
            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED, seed=seed,
        )
        refined_audio = samples.tensors[1].to(device=audio.device, dtype=audio.dtype)
        # Guarantee exact protected values even with a sampler that changes masked output.
        refined_audio = torch.where(mask.tensors[1] == 0, audio, refined_audio)
        out = latent.copy()
        out["samples"] = comfy.nested_tensor.NestedTensor((video, refined_audio))
        # Retain the original generation mask, not the temporary frozen-video mask.
        if boundary_latent is not None:
            original = latent.get("noise_mask", boundary_latent["noise_mask"])
            out["noise_mask"] = comfy.nested_tensor.NestedTensor((original.tensors[0], mask.tensors[1]))
        return (out,)


class SkebaH3AudioInpaintRange(SkebaH3AudioRefine):
    DESCRIPTION = ("Experimentally regenerate only a selected audio interval in a sampled H3 AV latent. "
                   "Video and audio outside the interval remain at their original latent values. "
                   "Connect the revised prompt conditioning, then decode and export this result to hear it.")

    @classmethod
    def INPUT_TYPES(cls):
        base = super().INPUT_TYPES()
        base["required"] = {**base["required"],
            "edit_start_seconds": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1000.0, "step": 0.025}),
            "edit_end_seconds": ("FLOAT", {"default": 3.0, "min": 0.0, "max": 1000.0, "step": 0.025}),
            "replace_locked_audio": ("BOOLEAN", {"default": True,
                "tooltip": "Reopen source audio that was locked by its original noise mask; a connected boundary_latent still protects its masked regions."}),
        }
        base["required"]["enabled"] = ("BOOLEAN", {"default": True})
        base["required"]["audio_denoise"] = ("FLOAT", {"default": 0.65, "min": 0.0, "max": 1.0, "step": 0.01})
        return base


class SkebaH3AudioEditMask:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "apply"
    RETURN_TYPES = ("LATENT", "STRING")
    RETURN_NAMES = ("latent", "status")
    DESCRIPTION = ("Before the H3 sampler, preserve source audio outside a selected interval "
                   "and regenerate that interval during the normal video/audio pass. "
                   "The existing video noise mask is preserved.")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent": ("LATENT",),
            "enabled": ("BOOLEAN", {"default": True}),
            "edit_start_seconds": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1000.0, "step": 0.025}),
            "edit_end_seconds": ("FLOAT", {"default": 3.0, "min": 0.0, "max": 1000.0, "step": 0.025}),
            "audio_mask_strength": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01,
                                      "tooltip": "0 locks the source audio; 1 fully regenerates the selected interval."}),
        }}

    def apply(self, latent, enabled=True, edit_start_seconds=1.0, edit_end_seconds=3.0,
              audio_mask_strength=0.5):
        if not enabled:
            return (latent, "Audio edit mask disabled; input latent unchanged.")
        video, audio = av_streams(latent)
        start, end, strength = float(edit_start_seconds), float(edit_end_seconds), float(audio_mask_strength)
        duration = audio.shape[-1] / 40.0
        if not 0 <= start < end <= duration:
            raise ValueError(f"SKEBA Audio Edit Mask: range must satisfy 0 <= start < end <= {duration:g} seconds.")
        if not 0 <= strength <= 1:
            raise ValueError("SKEBA Audio Edit Mask: strength must be between zero and one.")
        first, last = round(start * 40), round(end * 40)
        if last <= first:
            raise ValueError("SKEBA Audio Edit Mask: range is shorter than one 40 Hz audio-latent frame.")
        existing = latent.get("noise_mask")
        if existing is None:
            video_mask = torch.ones((video.shape[0], 1, *video.shape[2:]),
                                    device=video.device, dtype=torch.float32)
        elif getattr(existing, "is_nested", False) and len(existing.tensors) == 2:
            video_mask = existing.tensors[0]
        else:
            raise ValueError("SKEBA Audio Edit Mask: expected a packed H3 video/audio noise mask.")
        audio_mask = torch.zeros((audio.shape[0], 1, audio.shape[2], audio.shape[3]),
                                 device=audio.device, dtype=torch.float32)
        audio_mask[..., first:last] = strength
        output = latent.copy()
        output["noise_mask"] = comfy.nested_tensor.NestedTensor((video_mask, audio_mask))
        status = json.dumps({"edit_start_seconds": first / 40, "edit_end_seconds": last / 40,
                             "audio_mask_strength": strength,
                             "outside_audio": "locked", "video_mask": "preserved"})
        return (output, status)


def _h3_video_token_frames(count):
    """H3 temporal VAE coverage: first token is one frame, then four per token."""
    return 0 if count <= 0 else 1 + 4 * (count - 1)


class SkebaH3VideoEditMask:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "apply"
    RETURN_TYPES = ("LATENT", "STRING")
    RETURN_NAMES = ("latent", "status")
    DESCRIPTION = ("Before sampling, regenerate only the selected source-video interval. "
                   "Video outside it stays locked; the incoming audio mask is preserved. "
                   "Place this before SKEBA H3 Audio Edit Mask.")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent": ("LATENT",),
            "enabled": ("BOOLEAN", {"default": True}),
            "edit_start_seconds": ("FLOAT", {"default": 3.0, "min": 0.0, "max": 1000.0, "step": 0.025}),
            "edit_end_seconds": ("FLOAT", {"default": 10.0, "min": 0.0, "max": 1000.0, "step": 0.025}),
            "video_mask_strength": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01}),
            "extend_to_last_frame": ("BOOLEAN", {"default": False,
                "tooltip": "Include every remaining video-latent token, including H3's padded tail beyond the prompt's nominal seconds."}),
        }}

    def apply(self, latent, enabled=True, edit_start_seconds=3.0, edit_end_seconds=10.0,
              video_mask_strength=0.25, extend_to_last_frame=False):
        if not enabled:
            return (latent, "Video edit mask disabled; input latent unchanged.")
        video, audio = av_streams(latent)
        start, requested_end, strength = (float(edit_start_seconds), float(edit_end_seconds),
                                          float(video_mask_strength))
        duration = _h3_video_token_frames(video.shape[2]) / 24.0
        if not (math.isfinite(start) and math.isfinite(requested_end)
                and 0 <= start < requested_end and start < duration
                and (extend_to_last_frame or requested_end <= duration)):
            raise ValueError(f"SKEBA Video Edit Mask: use 0 <= start < end and start < {duration:g} seconds; end must fit unless Extend to last frame is enabled.")
        if not math.isfinite(strength) or not 0 <= strength <= 1:
            raise ValueError("SKEBA Video Edit Mask: strength must be between zero and one.")
        end = duration if extend_to_last_frame else requested_end
        start_frame, end_frame = start * 24.0, end * 24.0
        first = next((i for i in range(video.shape[2])
                      if _h3_video_token_frames(i + 1) > start_frame), video.shape[2])
        last = (video.shape[2] if extend_to_last_frame else
                next((i for i in range(first, video.shape[2])
                      if _h3_video_token_frames(i) >= end_frame), video.shape[2]))
        if last <= first:
            raise ValueError("SKEBA Video Edit Mask: range is shorter than one video-latent token.")
        existing = latent.get("noise_mask")
        if existing is None:
            audio_mask = torch.ones((audio.shape[0], 1, audio.shape[2], audio.shape[3]),
                                    device=audio.device, dtype=torch.float32)
        elif getattr(existing, "is_nested", False) and len(existing.tensors) == 2:
            audio_mask = existing.tensors[1]
        else:
            raise ValueError("SKEBA Video Edit Mask: expected a packed H3 video/audio noise mask.")
        video_mask = torch.zeros((video.shape[0], 1, *video.shape[2:]),
                                 device=video.device, dtype=torch.float32)
        video_mask[:, :, first:last] = strength
        output = latent.copy()
        output["noise_mask"] = comfy.nested_tensor.NestedTensor((video_mask, audio_mask))
        status = json.dumps({"video_requested_seconds": [start, requested_end],
                             "video_effective_seconds": [_h3_video_token_frames(first) / 24.0,
                                                         _h3_video_token_frames(last) / 24.0],
                             "video_mask_strength": strength,
                             "extend_to_last_frame": bool(extend_to_last_frame),
                             "masked_video_tokens": [first, last],
                             "video_token_count": int(video.shape[2]),
                             "outside_video": "locked",
                             "audio_mask": "preserved"})
        return (output, status)


class SkebaH3VideoLatentAnchorBlend:
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "blend"
    RETURN_TYPES = ("LATENT", "STRING")
    RETURN_NAMES = ("latent", "status")
    DESCRIPTION = ("Blend learned upscaled H3 video with a spatially resized copy of the "
                   "completed base-pass video latent. Higher anchor strength protects base-pass "
                   "identity more strongly but reduces learned upscale detail.")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "learned_upscale": ("LATENT",),
            "completed_base_video": ("LATENT",),
            "anchor_strength": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.01}),
        }}

    def blend(self, learned_upscale, completed_base_video, anchor_strength=0.3):
        learned = learned_upscale.get("samples")
        base = completed_base_video.get("samples")
        if (not isinstance(learned, torch.Tensor) or not isinstance(base, torch.Tensor)
                or learned.ndim != 5 or base.ndim != 5
                or learned.shape[:3] != base.shape[:3] or learned.shape[1] != 24):
            raise ValueError("SKEBA Video Latent Anchor Blend: connect matching H3 video latents from the same base pass.")
        strength = float(anchor_strength)
        if not math.isfinite(strength) or not 0 <= strength <= 1:
            raise ValueError("SKEBA Video Latent Anchor Blend: anchor strength must be between zero and one.")
        if strength == 0:
            return (learned_upscale, "Anchor disabled; learned upscale unchanged.")
        if learned.shape[-2:] != base.shape[-2:]:
            base = comfy.utils.common_upscale(base, learned.shape[-1], learned.shape[-2],
                                              "bilinear", "disabled")
        base = base.to(device=learned.device, dtype=learned.dtype)
        output = learned_upscale.copy()
        output["samples"] = learned.lerp(base, strength)
        status = json.dumps({"anchor_strength": strength, "learned_weight": 1 - strength,
                             "video_shape": list(output["samples"].shape),
                             "audio": "not processed"})
        return (output, status)


class SkebaH3AVInpaintRange(SkebaH3AudioRefine):
    CATEGORY = "Skeba AI Nodes - Reference/Experimental"
    FUNCTION = "inpaint"
    RETURN_TYPES = ("LATENT", "STRING")
    RETURN_NAMES = ("latent", "status")
    DESCRIPTION = ("Resample selected video and audio intervals in an encoded source or sampled H3 AV latent. "
                   "Each stream has its own time range and mask strength; all latent values "
                   "outside those ranges are preserved exactly. Video time uses H3's 24 fps "
                   "temporal tokens, so its effective boundary may expand by a few frames.")

    @classmethod
    def INPUT_TYPES(cls):
        base = super().INPUT_TYPES()
        common = base["required"]
        base["required"] = {
            "latent": common["latent"],
            "enabled": ("BOOLEAN", {"default": True}),
            "seed": common["seed"],
            "steps": common["steps"],
            "sampling_denoise": ("FLOAT", {"default": 0.65, "min": 0.0, "max": 1.0, "step": 0.01,
                "tooltip": "Shared denoise level for this extra inpaint pass; mask strengths independently scale video and audio."}),
            "cfg": common["cfg"],
            "sampler_name": common["sampler_name"],
            "scheduler": common["scheduler"],
            "video_start_seconds": ("FLOAT", {"default": 4.0, "min": 0.0, "max": 1000.0, "step": 0.025}),
            "video_end_seconds": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 1000.0, "step": 0.025}),
            "video_mask_strength": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01}),
            "audio_start_seconds": ("FLOAT", {"default": 4.0, "min": 0.0, "max": 1000.0, "step": 0.025}),
            "audio_end_seconds": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 1000.0, "step": 0.025}),
            "audio_mask_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
        }
        base["optional"].pop("boundary_latent", None)
        return base

    def check_lazy_status(self, enabled, sampling_denoise, **kwargs):
        if not enabled or sampling_denoise == 0:
            return []
        return [name for name in ("model", "positive", "negative", "noise")
                if name in kwargs and kwargs[name] is None]

    @staticmethod
    def _range(start, end, duration, label):
        start, end = float(start), float(end)
        if not (math.isfinite(start) and math.isfinite(end)
                and 0 <= start < end <= duration):
            raise ValueError(f"SKEBA AV Inpaint: {label} range must satisfy 0 <= start < end <= {duration:g} seconds.")
        return start, end

    def inpaint(self, latent, enabled=True, seed=0, steps=8, sampling_denoise=0.65,
                cfg=1.0, sampler_name="euler", scheduler="simple",
                video_start_seconds=4.0, video_end_seconds=8.0, video_mask_strength=0.25,
                audio_start_seconds=4.0, audio_end_seconds=8.0, audio_mask_strength=1.0,
                model=None, positive=None, negative=None, noise=None):
        if not enabled or sampling_denoise == 0:
            return (latent, "AV inpaint disabled; input latent unchanged.")
        if model is None or positive is None or negative is None:
            raise ValueError("SKEBA AV Inpaint: connect model, positive and negative when enabled.")
        video, audio = av_streams(latent)
        video_steps = int(video.shape[2])
        audio_steps = int(audio.shape[-1])
        video_duration = _h3_video_token_frames(video_steps) / 24.0
        audio_duration = audio_steps / 40.0
        v_start, v_end = self._range(video_start_seconds, video_end_seconds, video_duration, "video")
        a_start, a_end = self._range(audio_start_seconds, audio_end_seconds, audio_duration, "audio")
        v_strength, a_strength = float(video_mask_strength), float(audio_mask_strength)
        if not (0 <= v_strength <= 1 and 0 <= a_strength <= 1):
            raise ValueError("SKEBA AV Inpaint: video and audio mask strengths must be between zero and one.")

        # Select every temporal token whose decoded frames intersect the requested interval.
        start_frame, end_frame = v_start * 24.0, v_end * 24.0
        v_first = next((i for i in range(video_steps)
                        if _h3_video_token_frames(i + 1) > start_frame), video_steps)
        v_last = next((i for i in range(v_first, video_steps)
                       if _h3_video_token_frames(i) >= end_frame), video_steps)
        a_first = round(a_start * 40)
        a_last = round(a_end * 40)
        if (v_strength > 0 and v_last <= v_first) or (a_strength > 0 and a_last <= a_first):
            raise ValueError("SKEBA AV Inpaint: selected range is shorter than one latent step.")

        video_mask = torch.zeros((video.shape[0], 1, *video.shape[2:]), device=video.device, dtype=torch.float32)
        audio_mask = torch.zeros((audio.shape[0], 1, audio.shape[2], audio_steps), device=audio.device, dtype=torch.float32)
        video_mask[:, :, v_first:v_last] = v_strength
        audio_mask[..., a_first:a_last] = a_strength
        status = json.dumps({
            "video_requested_seconds": [v_start, v_end],
            "video_effective_seconds": [_h3_video_token_frames(v_first) / 24.0,
                                        _h3_video_token_frames(v_last) / 24.0],
            "video_mask_strength": v_strength,
            "audio_effective_seconds": [a_first / 40.0, a_last / 40.0],
            "audio_mask_strength": a_strength,
            "outside_ranges": "original sampled latent retained",
        })
        if not torch.any(video_mask) and not torch.any(audio_mask):
            return (latent, status)
        mask = comfy.nested_tensor.NestedTensor((video_mask, audio_mask))
        if noise is None:
            noise_samples = comfy.sample.prepare_noise(latent["samples"], seed, latent.get("batch_index"))
        else:
            seed = noise.seed
            noise_samples = noise.generate_noise(latent)
        samples = comfy.sample.sample(
            model, noise_samples, steps, cfg, sampler_name, scheduler, positive, negative,
            latent["samples"], denoise=sampling_denoise, noise_mask=mask,
            callback=latent_preview.prepare_callback(model, steps),
            disable_pbar=not comfy.utils.PROGRESS_BAR_ENABLED, seed=seed,
        )
        refined_video = samples.tensors[0].to(device=video.device, dtype=video.dtype)
        refined_audio = samples.tensors[1].to(device=audio.device, dtype=audio.dtype)
        out = latent.copy()
        out["samples"] = comfy.nested_tensor.NestedTensor((
            torch.where(video_mask == 0, video, refined_video),
            torch.where(audio_mask == 0, audio, refined_audio),
        ))
        return (out, status)
