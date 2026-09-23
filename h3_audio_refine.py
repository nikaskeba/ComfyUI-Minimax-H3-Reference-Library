"""Optional audio refinement adapted from Adudeguyman/ComfyUI-H3-AudioRefine.

MIT attribution: LICENSES/ComfyUI-H3-AudioRefine.txt.
"""

import torch
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


def refinement_mask(latent, boundary_latent=None):
    video, audio = av_streams(latent)
    audio_mask = torch.ones_like(audio, dtype=torch.float32)
    for source in (latent, boundary_latent):
        if source is None:
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
               positive=None, negative=None, boundary_latent=None, noise=None):
        if not enabled or audio_denoise == 0:
            return (latent,)
        if model is None or positive is None or negative is None:
            raise ValueError("SKEBA Audio Refine: connect model, positive and negative when enabled.")
        mask = refinement_mask(latent, boundary_latent)
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
