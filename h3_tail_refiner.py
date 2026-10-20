"""Standalone, tail-window adaptation of noEmbryo's H3 Clip Refiner.

The bundled refiner below is adapted from ComfyUI-noEmbryo/minimax.py.
MIT License, Copyright (c) 2016-2019 noEmbryo. See NOEMBRYO_LICENSE.txt.
"""

import logging

import torch
import comfy.model_management
import comfy.nested_tensor
import comfy.sample
import comfy.samplers
from comfy.utils import ProgressBar

try:
    from comfy_execution.graph_utils import get_original_node_id
except ImportError:
    get_original_node_id = None

log_ = logging.getLogger("skeba_h3_tail_refiner")


def _steps_for_frames(frames):
    return {5: 2, 22: 7, 39: 12, 56: 17}.get(int(frames))

def _band_gauss1d(sigma, device, dtype):
    r = max(1, int(round(3.0 * float(sigma))))
    x = torch.arange(-r, r + 1, dtype=torch.float32, device=device)
    k = torch.exp(-(x * x) / (2.0 * float(sigma) ** 2))
    return (k / k.sum()).to(dtype)


def _band_split(t, sigma=2.0):
    """Separable Gaussian low/high split over the last two dims. -> (lo, hi).

    Returns None when the tensor has no spatial extent to speak of.
    Replicate padding, not reflect: a latent's spatial dims are small and
    reflect needs the pad to be smaller than the dimension.
    """
    if t.dim() < 2 or t.shape[-1] < 8 or t.shape[-2] < 8:
        return None
    # noinspection PyUnresolvedReferences
    import torch.nn.functional as f
    h, w = int(t.shape[-2]), int(t.shape[-1])
    flat = t.reshape(-1, 1, h, w)
    k = _band_gauss1d(sigma, t.device, t.dtype)
    pad = k.numel() // 2
    lo = f.conv2d(f.pad(flat, (pad, pad, 0, 0), mode="replicate"),
                  k.view(1, 1, 1, -1))
    lo = f.conv2d(f.pad(lo, (0, 0, pad, pad), mode="replicate"),
                  k.view(1, 1, -1, 1))
    lo = lo.reshape(t.shape)
    return lo, t - lo


def _high_band_sd(t, sigma=2.0):
    """Absolute high-band standard deviation. -> float, or None.

    The band *ratio* only drifts ~1.6% across a chain (0.3643 -> 0.3702),
    so a gain match on the ratio moves a tiny delta that strength cannot
    amplify visibly. The absolute high-band sigma can drift much more when
    the total sigma also grows, so matching the absolute value gives a
    correction delta that is large enough for strength to move.
    """
    got = _band_split(t, sigma)
    if got is None:
        return None
    _, hi = got
    hi_sd = float(hi.float().std())
    if not hi_sd or hi_sd != hi_sd:
        return None
    return hi_sd


class _AVStreamPair:
    """Minimal stand-in for a NestedTensor: wraps (video, audio) tensors and
    exposes the unbind() interface that comfy-core's LTXVSeparateAVLatent
    (and the H3 sampler code) expects. The wrapped tensors are always dense,
    detached, contiguous copies, so they are safe to feed to the VAE kernels.
    """

    def __init__(self, video, audio):
        self._parts = [video, audio]

    def unbind(self):
        # noinspection PyTypeChecker
        return tuple(self._parts)

    def __iter__(self):
        return iter(self._parts)

    def __len__(self):
        return len(self._parts)


def _refine_resample(av_latent, model, positive, negative, denoise, steps, cfg,
                     sampler_name, scheduler, seed, node_id=None):
    """ A short, low-denoise second sample of a finished AV latent.

    av_latent is the full H3 AV latent (NestedTensor or tuple of [video, audio]).
    Returns the refined video latent on CPU [B,C,T,H,W].
    The model expects the full AV latent (video + audio) for the forward pass.

    :return: torch.Tensor [B,C,T,H,W] on CPU (video only)|None
    """
    device = model.load_device
    # Move AV latent to device - handle NestedTensor or tuple
    if hasattr(av_latent, "to"):
        work = av_latent.to(device)
    elif isinstance(av_latent, (tuple, list)):
        work = tuple(p.to(device) for p in av_latent)
    else:
        work = av_latent.to(device)

    # Progress bar for refine resample steps
    pbar = ProgressBar(int(steps), node_id=node_id)

    # noinspection PyUnusedLocal
    def _pbar_callback(step, x0, x, total_steps):
        pbar.update_absolute(step + 1, total_steps)

    try:
        noise = comfy.sample.prepare_noise(work, int(seed))
        samples = comfy.sample.sample(model, noise, int(steps), float(cfg),
                                      str(sampler_name), str(scheduler),
                                      positive, negative, work, denoise=float(denoise),
                                      seed=int(seed), callback=_pbar_callback)
        # samples is AV latent (NestedTensor/tuple); extract video part
        if hasattr(samples, "unbind"):
            video = list(samples.unbind())[0]
        elif isinstance(samples, (tuple, list)):
            video = samples[0]
        else:
            video = samples
        return video.detach().to("cpu", copy=True).contiguous()
    finally:
        del work
        comfy.model_management.soft_empty_cache()


class H3ClipRefiner:
    """ Inline style-drift corrector for H3 Motion Context clips.

    Place this node BETWEEN the sampler (SamplerCustomAdvanced) and the
    H3 Motion Context Save Latent node. It operates on the LATENT level
    (no VAE decode/encode needed) to fix the style drift that accumulates
    across clips in a chain.

    The drift has four components:
    1. Luminance drift (mean shift)
    2. Contrast drift (std change)
    3. Color/saturation drift (per-channel mean and std changes)
    4. Texture ratchet (high-band noise/grain increase)

    TWO HALVES:
    * Statistical (always on): a per-channel affine (matches mean + std)
      followed by a high-band gain match. This fixes the DRIFT but, being
      pure arithmetic, cannot put back micro-detail the chain has lost.
    * Generative (optional): connect model + positive/negative and the node
      runs a short low-denoise REFINE RESAMPLE, then transfers ONLY its
      high band (detail) onto the original low band (structure). Keeping the
      original low band is what stops the background shift / dissolve that a
      whole-latent blend (e.g. H3-LongTakeNoCuts) suffers from.

    UNITS: context_length is in FRAMES (5/22/39/56), matching the Motion
    Context node and the Stitcher. The latent's time axis is in TOKENS, so it
    is converted with _steps_for_frames (22 frames -> 7 tokens) before the
    head/body/tail split.

    WORKFLOW:
    1. Run the FIRST clip through with reference_latent unconnected.
       The node measures and reports its statistics but passes the latent
       through unchanged.
    2. Feed that first clip's latent into reference_latent for all
       subsequent clips. The node matches every later clip to the first.
    3. (Optional) connect model + positive/negative to also regenerate lost
       detail; tune refine_denoise (~0.3-0.5) and detail_strength.
    4. Adjust strength if needed: 1.0 = full match, >1.0 = stronger.
    5. Set context_length to match your H3 Motion Context setting (default 22).
    """
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"latent": ("LATENT", {
            "tooltip": "The generated AV latent from your H3 sampler "
                       "(SamplerCustomAdvanced output)."}),
            "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0,
                "step": 0.01,
                "tooltip": "Correction strength. 0.0 = measure only (pass through).\n"
                           "1.0 = full match to reference statistics.\n"
                           ">1.0 = overshoot (pushes past the reference)."}),
            "context_length": (["5", "22", "39", "56"], {"default": "22",
                "tooltip": "Number of frames at head/tail that are the Motion Context "
                           "overlap regions. Must match the context_length in "
                           "H3 Motion Context and Clip Stitcher."}),
            },
            "optional": {"reference_latent": ("LATENT", {
                "tooltip": "Reference latent (e.g., first clip). When connected, "
                           "all target statistics are measured from this latent "
                           "and the input latent is corrected to match it."}),
                "model": ("MODEL", {
                    "tooltip": "Optional. Connect your H3 model to enable the "
                               "refine resample: a short low-denoise second "
                               "sample that regenerates the micro-detail the "
                               "chain loses. Leave disconnected for the pure "
                               "statistical corrector."}),
                "positive": ("CONDITIONING", {
                    "tooltip": "Positive conditioning for the refine resample "
                               "(same prompt you sampled the clip with)."}),
                "negative": ("CONDITIONING", {
                    "tooltip": "Negative conditioning for the refine resample."}),
                "refine_denoise": ("FLOAT", {"default": 0.4, "min": 0.0, "max": 1.0,
                    "step": 0.01,
                    "tooltip": "Denoise for the refine resample. ~0.3-0.5 restores "
                               "detail while keeping the structure (only the high "
                               "band is transferred, so the background cannot shift). "
                               "Higher changes content more."}),
                "refine_steps": ("INT", {"default": 3, "min": 1, "max": 50,
                    "tooltip": "Sampler steps for the refine resample. 2-4 is plenty."}),
                "refine_cfg": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 100.0,
                    "step": 0.1,
                    "tooltip": "CFG for the refine resample. Match your main sampler."}),
                "sampler_name": (comfy.samplers.SAMPLER_NAMES, {
                    "default": "euler",
                    "tooltip": "Sampler for the refine resample."}),
                "scheduler": (comfy.samplers.SCHEDULER_NAMES, {
                    "default": "normal",
                    "tooltip": "Scheduler for the refine resample."}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff,
                    "control_after_generate": True,
                    "tooltip": "Seed for the refine resample noise."}),
                "detail_strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0,
                    "step": 0.01,
                    "tooltip": "How much of the refined high band (detail) to "
                               "transfer over the original. 0 = statistical only, "
                               "1 = full refined detail. The low band (structure) "
                               "is always kept from the original, so the background "
                               "never shifts."}),
                },
            }

    RETURN_TYPES = ("LATENT", "STRING")
    RETURN_NAMES = ("latent", "report")
    FUNCTION = "refine"
    CATEGORY = "noEmbryo/MiniMax H3"
    DESCRIPTION = ("Inline style-drift corrector + optional refine resample for "
                   "H3 Motion Context clips.\n"
                   "Place between SamplerCustomAdvanced and H3 Motion Context Save Latent.\n"
                   "Statistical half fixes luminance/contrast/color/texture drift; "
                   "connect model+conditioning to also regenerate lost micro-detail.\n"
                   "strength=0: measure only. strength=1.0: full match. >1: stronger.")

    # noinspection PyUnusedLocal
    @classmethod
    def IS_CHANGED(cls, latent, strength, context_length, reference_latent=None,
                   model=None, positive=None, negative=None, refine_denoise=0.4,
                   refine_steps=3, refine_cfg=1.0, sampler_name="euler",
                   scheduler="normal", seed=0, detail_strength=1.0):
        # noinspection PyBroadException
        try:
            import hashlib
            latent_bytes = str(latent).encode()
            latent_hash = hashlib.md5(latent_bytes).hexdigest()[:16]
            return (latent_hash, float(strength), int(context_length),
                    None if model is None else id(model),
                    float(refine_denoise), int(refine_steps), float(refine_cfg),
                    str(sampler_name), str(scheduler), int(seed),
                    float(detail_strength))
        except Exception:
            return float("NaN")

    @staticmethod
    def refine(latent, strength, context_length, reference_latent=None,
               model=None, positive=None, negative=None, refine_denoise=0.4,
               refine_steps=3, refine_cfg=1.0, sampler_name="euler",
               scheduler="normal", seed=0, detail_strength=1.0):
        # Extract video and audio from AV latent
        if not isinstance(latent, dict) or "samples" not in latent:
            raise ValueError("H3ClipRefiner: expected a latent dict with 'samples' key")
        
        samples = latent["samples"]
        if hasattr(samples, "unbind"):
            parts = list(samples.unbind())
        elif isinstance(samples, (tuple, list)):
            parts = list(samples)
        else:
            raise ValueError("H3ClipRefiner: expected AV latent with video+audio")
        
        if len(parts) < 2:
            raise ValueError("H3ClipRefiner: latent has no audio stream")
        
        video_latent = parts[0].detach().to("cpu", copy=True).contiguous()
        audio_latent = parts[1].detach().to("cpu", copy=True).contiguous()
        
        # Handle video latent shape: [B,C,T,H,W] or [C,T,H,W]
        had_batch = False
        if video_latent.dim() == 5:
            if video_latent.shape[0] != 1:
                raise ValueError("H3ClipRefiner: only batch size 1 is supported, "
                                 "got video shape %s." % (tuple(video_latent.shape),))
            had_batch = True
            video_latent = video_latent.squeeze(0)  # [C,T,H,W]
        
        c, t, h, w = video_latent.shape
        # context_length is in FRAMES (5/22/39/56), but the latent's time axis
        # is in TOKENS. Convert first (22 frames -> 7 tokens) so the head/body/
        # tail split lines up with the frames the Stitcher actually crossfades.
        # Splitting by the raw frame count here was a units bug that kept far
        # too much (or, on short clips, the whole clip) out of the correction.
        overlap = _steps_for_frames(context_length) or 0

        # --- Split into head / body / tail along the temporal axis ---
        # The head (first `overlap` tokens) and tail (last `overlap` tokens)
        # are the Motion Context overlap regions that the Clip Stitcher
        # crossfades with the adjacent clips.
        #
        # NEW BEHAVIOUR: We now CORRECT the head/tail to match the corrected
        # body statistics. This eliminates the pulsing effect (bright head/tail
        # vs normal body) while keeping the crossfade smooth because ALL clips'
        # overlap regions are corrected to match the same reference target.
        if overlap > 0 and t >= 2 * overlap:
            head = video_latent[:, :overlap]              # [C, overlap, H, W]
            body = video_latent[:, overlap:t - overlap]   # [C, body, H, W]
            tail = video_latent[:, t - overlap:]          # [C, overlap, H, W]
            has_overlap = True
        else:
            # Clip too short to have a meaningful overlap region; treat the
            # whole clip as body (old behaviour) so short clips still work.
            head = None
            body = video_latent
            tail = None
            has_overlap = False

        # --- Optional refine resample (the generative half of the fix) ---
        # A short low-denoise second sample regenerates the micro-detail the
        # chain loses. Only its HIGH band is used later (detail transfer), so
        # the original low band -- the structure/background -- is never
        # disturbed and cannot shift the way a whole-latent blend does.
        refined_body = None
        if model is not None and positive is not None and detail_strength > 0.0:
            if negative is None:
                log_.warning("H3ClipRefiner: negative conditioning not connected; "
                             "refine resample requires both positive and negative. "
                             "Skipping detail transfer.")
            else:
                try:
                    # Use the full AV latent (video + audio) for the model forward pass
                    av_latent = latent["samples"]
                    log_.info("H3ClipRefiner: starting refine resample "
                              "(denoise=%.2f, steps=%d, cfg=%.2f, seed=%d)...",
                              refine_denoise, refine_steps, refine_cfg, int(seed))
                    # noinspection PyCallingNonCallable
                    node_id = get_original_node_id() if get_original_node_id is not None else None
                    # noinspection PyNoneFunctionAssignment
                    refined_video = _refine_resample(av_latent, model, positive, negative,
                                                      refine_denoise, refine_steps,
                                                      refine_cfg, sampler_name, scheduler,
                                                      seed, node_id)
                    # noinspection PyUnresolvedReferences
                    refined_video = refined_video.to(video_latent.dtype)
                    log_.info("H3ClipRefiner: refine resample returned video shape %s",
                              tuple(refined_video.shape))
                    # refined_video is [B,C,T,H,W] or [C,T,H,W]; remove batch dim if present
                    if refined_video.dim() == 5:
                        refined_video = refined_video[0]
                    if tuple(refined_video.shape) == tuple(video_latent.shape):
                        if has_overlap:
                            refined_head = refined_video[:, :overlap]
                            refined_body = refined_video[:, overlap:t - overlap]
                            refined_tail = refined_video[:, t - overlap:]
                        else:
                            refined_head = None
                            refined_body = refined_video
                            refined_tail = None
                        log_.info("H3ClipRefiner: refine resample done "
                                  "(denoise=%.2f, steps=%d, cfg=%.2f).",
                                  refine_denoise, refine_steps, refine_cfg)
                    else:
                        log_.warning("H3ClipRefiner: refine resample returned %s, "
                                     "expected %s; skipping detail transfer.",
                                     tuple(refined_video.shape),
                                     tuple(video_latent.shape))
                        refined_head = refined_body = refined_tail = None
                except Exception as e:
                    log_.warning("H3ClipRefiner: refine resample failed (%s); "
                                 "using statistical correction only.", e)
                    import traceback
                    tb = traceback.format_exc()
                    log_.warning("H3ClipRefiner: refine resample traceback:\n%s", tb)
                    refined_body = None

        body_flat = body.reshape(c * body.shape[1], h, w)
        # noinspection PyUnusedLocal
        flat_latent = video_latent.reshape(c * t, h, w)
        
        # --- Measure current statistics (from BODY only) ---
        current_mean = float(body_flat.mean())
        current_std = float(body_flat.std())
        current_channel_means = body.mean(dim=(1, 2, 3))  # [C]
        current_channel_stds = body.std(dim=(1, 2, 3))    # [C]
        
        hi_sds = []
        for s in [1.0, 2.0, 3.0]:
            hs = _high_band_sd(body_flat, sigma=s)
            if hs is not None:
                hi_sds.append(hs)
        current_hi_sd = sum(hi_sds) / len(hi_sds) if hi_sds else None

        # --- Determine target statistics ---
        target_mean = current_mean
        target_std_val = current_std
        target_channel_means = current_channel_means.clone()
        target_channel_stds = current_channel_stds.clone()
        target_hi_sd = current_hi_sd

        if reference_latent is not None:
            # Measure all targets from reference latent
            if not isinstance(reference_latent, dict) or "samples" not in reference_latent:
                raise ValueError("H3ClipRefiner: reference_latent must be an AV latent dict")
            ref_samples = reference_latent["samples"]
            if hasattr(ref_samples, "unbind"):
                ref_parts = list(ref_samples.unbind())
            elif isinstance(ref_samples, (tuple, list)):
                ref_parts = list(ref_samples)
            else:
                raise ValueError("H3ClipRefiner: reference_latent must be AV latent")
            if len(ref_parts) < 2:
                raise ValueError("H3ClipRefiner: reference_latent has no audio stream")
            ref_video = ref_parts[0].detach().to("cpu", copy=True).contiguous()
            if ref_video.dim() == 5:
                ref_video = ref_video.squeeze(0)
            # Measure the reference from its BODY too, so the target reflects
            # the same region we are correcting (apples to apples).
            ref_overlap = overlap
            if ref_overlap > 0 and ref_video.shape[1] >= 2 * ref_overlap:
                ref_body = ref_video[:, ref_overlap:ref_video.shape[1] - ref_overlap]
            else:
                ref_body = ref_video
            ref_flat = ref_body.reshape(-1, ref_body.shape[-2], ref_body.shape[-1])

            target_mean = float(ref_flat.mean())
            target_std_val = float(ref_flat.std())
            target_channel_means = ref_body.mean(dim=(1, 2, 3))
            target_channel_stds = ref_body.std(dim=(1, 2, 3))

            ref_hi_sds = []
            for s in [1.0, 2.0, 3.0]:
                hs = _high_band_sd(ref_flat, sigma=s)
                if hs is not None:
                    ref_hi_sds.append(hs)
            if ref_hi_sds:
                target_hi_sd = sum(ref_hi_sds) / len(ref_hi_sds)

            log_.info("H3ClipRefiner: measured targets from reference_latent: "
                      "mean=%.4f, std=%.4f, hi_sd=%.4f",
                      target_mean, target_std_val, target_hi_sd)

        # --- Build report ---
        report_parts = ["H3ClipRefiner: mean=%.4f->%.4f" % (current_mean, target_mean),
                        "std=%.4f->%.4f" % (current_std, target_std_val),]
        if current_hi_sd is not None:
            report_parts.append("hi_sd=%.4f->%.4f" % (current_hi_sd, target_hi_sd))
        else:
            report_parts.append("hi_sd=N/A")

        # Check if any correction is needed
        needs_correction = False
        if abs(target_mean - current_mean) > 1e-6:
            needs_correction = True
        if abs(target_std_val - current_std) > 1e-6:
            needs_correction = True
        if (target_channel_means - current_channel_means).abs().max() > 1e-6:
            needs_correction = True
        if current_hi_sd is not None and target_hi_sd is not None:
            if abs(target_hi_sd - current_hi_sd) > 1e-6:
                needs_correction = True
        
        # Nothing to do at all: no refine requested AND the statistics already
        # match (or strength is 0). Pass the latent through untouched.
        if refined_body is None and (strength <= 0 or not needs_correction):
            report = ", ".join(report_parts)
            report += " [MEASURE ONLY - latent passed through]"
            return latent, report

        band_gain = None
        corrected_body = body

        # --- 1. Statistical correction (drift): per-channel affine ---
        # Skipped when strength is 0 or the stats already match; the detail
        # transfer below can still run on its own in that case.
        if strength > 0 and needs_correction:
            a = torch.ones(c, device=video_latent.device, dtype=video_latent.dtype)
            b = torch.zeros(c, device=video_latent.device, dtype=video_latent.dtype)

            for ch in range(c):
                ch_data = body[ch]  # [T_body, H, W]
                ch_mean = float(ch_data.mean())
                ch_std = float(ch_data.std())
                if ch_std < 1e-6:
                    ch_std = 1e-6

                tgt_ch_mean = float(target_channel_means[ch])
                tgt_ch_std = float(target_channel_stds[ch])

                scale = tgt_ch_std / ch_std
                shift = tgt_ch_mean - scale * ch_mean

                a[ch] = scale
                b[ch] = shift

            corrected_body = body * a.view(c, 1, 1, 1) + b.view(c, 1, 1, 1)
            log_.info("H3ClipRefiner: per-channel affine: a=%s, b=%s",
                      a.tolist(), b.tolist())

            # 2a. Statistical high-band energy correction (texture ratchet).
            #     Only when there is no refine supplying real detail. Match the
            #     ABSOLUTE high-band std, measured and applied on the same
            #     affine-corrected body so the two stay consistent.
            if refined_body is None and current_hi_sd is not None \
                    and target_hi_sd is not None:
                if abs(target_hi_sd - current_hi_sd) > 1e-6:
                    corr_body_flat = corrected_body.reshape(c * body.shape[1], h, w)
                    corr_split = _band_split(corr_body_flat, sigma=2.0)
                    if corr_split is not None:
                        corr_lo, corr_hi = corr_split
                        cur_hi = float(corr_hi.float().std())
                        if cur_hi > 1e-6:
                            # 1:1 match gain for absolute high-band std:
                            # k * cur_hi = target_hi_sd  =>  k = target / cur
                            k_1to1 = target_hi_sd / cur_hi
                            k_1to1 = min(max(k_1to1, 0.05), 5.0)
                            corrected_body = (corr_lo + corr_hi * k_1to1).reshape(
                                c, body.shape[1], h, w)
                            band_gain = k_1to1
                            report_parts.append("band_gain=%.4f" % band_gain)
                        else:
                            report_parts.append("band_correction_failed")
                    else:
                        report_parts.append("band_correction_failed")

            # 3. Apply strength to the statistical correction delta.
            corrected_body = body + (corrected_body - body) * strength

        # Initialize corrected_head/tail to original head/tail for detail transfer
        if has_overlap:
            corrected_head = head
            corrected_tail = tail

        # --- 2b. Detail transfer from the refine resample (generative) ---
        # Keep the (possibly affine-corrected) LOW band -- the structure, so
        # the background cannot shift -- and blend in the refined HIGH band
        # (regenerated micro-detail). detail_strength dials 0..1. This is what
        # restores detail the statistical half cannot, without the dissolve a
        # whole-latent blend would introduce.
        # Apply to body, head, and tail for consistency across the entire clip.
        if refined_body is not None:
            log_.info("H3ClipRefiner: performing detail transfer (strength=%.2f)...",
                      detail_strength)
            d = float(min(max(detail_strength, 0.0), 1.0))

            # Helper to apply detail transfer to a region
            # noinspection PyShadowingNames
            def _detail_transfer(corrected_reg, refined_reg, region_name):
                if corrected_reg is None or refined_reg is None:
                    return corrected_reg
                corr_flat = corrected_reg.reshape(c * corrected_reg.shape[1], h, w)
                ref_flat = refined_reg.reshape(c * refined_reg.shape[1], h, w)
                corr_split = _band_split(corr_flat, sigma=2.0)
                ref_split = _band_split(ref_flat, sigma=2.0)
                if corr_split is not None and ref_split is not None:
                    corr_lo, corr_hi = corr_split
                    _, ref_hi = ref_split
                    mixed_hi = corr_hi * (1.0 - d) + ref_hi.to(corr_hi.dtype) * d
                    result = (corr_lo + mixed_hi).reshape(c, corrected_reg.shape[1], h, w)
                    log_.info("H3ClipRefiner: detail transfer applied to %s", region_name)
                    return result
                else:
                    log_.warning("H3ClipRefiner: detail transfer failed for %s "
                                 "- band split returned None", region_name)
                    return corrected_reg

            corrected_body = _detail_transfer(corrected_body, refined_body, "body")
            if has_overlap:
                # noinspection PyUnboundLocalVariable
                corrected_head = _detail_transfer(corrected_head, refined_head, "head")
                # noinspection PyUnboundLocalVariable
                corrected_tail = _detail_transfer(corrected_tail, refined_tail, "tail")
            report_parts.append("detail_transfer=%.2f" % d)
            log_.info("H3ClipRefiner: detail transfer applied successfully")

        # --- Correct head/tail to match corrected_body statistics ---
        # Only run if there's an actual correction (statistical or detail transfer).
        body_changed = not torch.allclose(corrected_body, body, rtol=1e-4, atol=1e-5)
        if has_overlap and (body_changed or refined_body is not None):
            # Measure corrected_body statistics (the target for head/tail)
            target_ch_means = corrected_body.mean(dim=(1, 2, 3))  # [C]
            target_ch_stds = corrected_body.std(dim=(1, 2, 3))    # [C]

            # Helper to correct a region (head or tail) to match target stats
            def _correct_region(region, region_name):
                if region is None:
                    return None
                reg_ch_means = region.mean(dim=(1, 2, 3))
                reg_ch_stds = region.std(dim=(1, 2, 3)).clamp(min=1e-6)

                # Per-channel affine to match corrected_body
                a_reg = target_ch_stds / reg_ch_stds
                b_reg = target_ch_means - a_reg * reg_ch_means
                corrected_reg = region * a_reg.view(c, 1, 1, 1) + b_reg.view(c, 1, 1, 1)

                # Apply strength to the correction delta (0 = no statistical correction)
                corrected_reg = region + (corrected_reg - region) * strength

                # Apply band_gain if it was computed (statistical path only)
                # Apply to the AFFINE-CORRECTED region's high band (consistent with body)
                if band_gain is not None:
                    reg_flat = corrected_reg.reshape(c * region.shape[1], h, w)
                    reg_split = _band_split(reg_flat, sigma=2.0)
                    if reg_split is not None:
                        reg_lo, reg_hi = reg_split
                        corrected_reg = (reg_lo + reg_hi * band_gain).reshape(
                            c, region.shape[1], h, w)

                log_.info("H3ClipRefiner: %s corrected to match body (a=%s, b=%s)",
                          region_name, a_reg.tolist(), b_reg.tolist())
                return corrected_reg

            # noinspection PyUnboundLocalVariable
            corrected_head = _correct_region(corrected_head, "head")
            # noinspection PyUnboundLocalVariable
            corrected_tail = _correct_region(corrected_tail, "tail")
        elif has_overlap:
            # No correction needed for body, keep head/tail as-is (already set above)
            pass

        # --- Reassemble: head/body/tail all corrected, no ramp needed ---
        # Statistics match exactly at boundaries, so no step discontinuity.
        # The crossfade sees consistently-corrected overlap regions on both sides.
        if has_overlap:
            # noinspection PyUnboundLocalVariable
            corrected = torch.cat([corrected_head, corrected_body, corrected_tail], dim=1)
        else:
            corrected = corrected_body

        # --- Build final report ---
        report = ", ".join(report_parts)
        tags = []
        if refined_body is not None:
            tags.append("refine+detail")
        if band_gain is not None:
            # noinspection PyStringFormat
            tags.append("gain=%.4f" % band_gain)
        tags.append("strength=%.2f" % strength)
        tags.append("ctx=%df/%dt" % (int(context_length), overlap))
        report += " [CORRECTED - " + ", ".join(tags) + "]"
        if has_overlap:
            report += " [overlap-corrected]"

        log_.info("H3ClipRefiner: applied correction, strength=%.2f, "
                  "ctx=%d frames/%d tokens", strength, int(context_length), overlap)
        
        # --- Reconstruct AV latent ---
        if had_batch:
            corrected = corrected.unsqueeze(0)
        
        out = dict(latent)
        out["samples"] = _AVStreamPair(corrected, audio_latent)
        
        return out, report


_WINDOW_STEPS = {5: 2, 22: 7, 39: 12, 56: 17}
_MOTION_AUDIO_END_KEY = "motion_context_audio_end_frame"


def _streams(latent):
    if not isinstance(latent, dict) or "samples" not in latent:
        raise ValueError("SKEBA tail refiner: expected an H3 AV latent dict")
    samples = latent["samples"]
    if hasattr(samples, "unbind"):
        parts = tuple(samples.unbind())
    elif isinstance(samples, (tuple, list)):
        parts = tuple(samples)
    else:
        raise ValueError("SKEBA tail refiner: expected paired video/audio streams")
    if len(parts) < 2 or parts[0].ndim != 5 or parts[1].ndim != 4:
        raise ValueError("SKEBA tail refiner: expected video [B,C,T,H,W] and "
                         "audio [B,C,2,T] streams")
    if parts[0].shape[0] != 1 or parts[1].shape[0] != 1:
        raise ValueError("SKEBA tail refiner: only batch size 1 is supported")
    return parts[0], parts[1]


def _tail_conditioning(conditioning):
    """Keep authored/media references, drop full-clip temporal anchors."""
    if conditioning is None:
        return None
    result = []
    for embedding, metadata in conditioning:
        values = dict(metadata)
        values.pop("minimax_keyframes", None)
        values.pop("minimax_frame_count", None)
        if "minimax_refs" in values:
            values["minimax_refs"] = [
                ref for ref in values["minimax_refs"]
                if _MOTION_AUDIO_END_KEY not in ref
            ]
        result.append([embedding, values])
    return result


class SkebaH3TailClipRefiner:
    """Refine only the final H3 window, then splice it into the full AV clip."""

    @classmethod
    def INPUT_TYPES(cls):
        # Keep the original widget and socket order so saved workflows can
        # replace noEmbryo's node without shuffling their settings.
        schema = H3ClipRefiner.INPUT_TYPES()
        schema["optional"]["refine_if_next_prompt"] = ("BOOLEAN", {
            "default": True,
            "tooltip": "Skip the extra refine sample on the final prompt, "
                       "when no continuation latent will be saved.",
        })
        return schema

    RETURN_TYPES = ("LATENT", "STRING")
    RETURN_NAMES = ("latent", "report")
    FUNCTION = "refine"
    CATEGORY = "Skeba AI Nodes - Motion Context"
    DESCRIPTION = ("Run the H3 detail-refine sample on only the final Motion "
                   "Context window, then put those video steps back into "
                   "the full AV latent. Audio remains unchanged.")

    @staticmethod
    def refine(latent, strength, context_length, reference_latent=None,
               model=None, positive=None, negative=None, refine_denoise=0.4,
               refine_steps=3, refine_cfg=1.0, sampler_name="euler",
               scheduler="normal", seed=0, detail_strength=1.0,
               refine_if_next_prompt=True):
        if not refine_if_next_prompt:
            return latent, "SKEBA tail refiner: skipped (final prompt)"
        video, audio = _streams(latent)
        frames = int(context_length)
        steps = _WINDOW_STEPS.get(frames)
        if steps is None:
            raise ValueError("SKEBA tail refiner: context_length must be "
                             "5, 22, 39, or 56 frames")
        if steps > video.shape[2]:
            raise ValueError("SKEBA tail refiner: input has fewer than %d "
                             "video steps for %d context frames" % (steps, frames))
        if (int(video.shape[2]) - steps) % 5:
            raise ValueError("SKEBA tail refiner: the selected video tail "
                             "starts off H3's five-step temporal grid")
        audio_steps = round(frames * 40 / 24)
        if audio_steps > audio.shape[-1]:
            raise ValueError("SKEBA tail refiner: input audio is shorter "
                             "than the selected picture context window")

        tail = {"samples": comfy.nested_tensor.NestedTensor((
            video[:, :, -steps:].contiguous(),
            audio[..., -audio_steps:].contiguous(),
        ))}
        ref_tail = None
        if reference_latent is not None:
            ref_video, ref_audio = _streams(reference_latent)
            if ref_video.shape[2] < steps or ref_audio.shape[-1] < audio_steps:
                raise ValueError("SKEBA tail refiner: reference latent is "
                                 "shorter than the requested context window")
            ref_tail = {"samples": comfy.nested_tensor.NestedTensor((
                ref_video[:, :, -steps:].contiguous(),
                ref_audio[..., -audio_steps:].contiguous(),
            ))}

        refined, report = H3ClipRefiner.refine(
            tail, strength, frames, reference_latent=ref_tail,
            model=model, positive=_tail_conditioning(positive),
            negative=_tail_conditioning(negative),
            refine_denoise=refine_denoise, refine_steps=refine_steps,
            refine_cfg=refine_cfg, sampler_name=sampler_name,
            scheduler=scheduler, seed=seed, detail_strength=detail_strength)
        refined_video, _ = _streams(refined)
        if refined_video.shape != video[:, :, -steps:].shape:
            raise RuntimeError("SKEBA tail refiner: refined video changed "
                               "shape; refusing to splice an incompatible tail")
        if torch.equal(refined_video.to(video.device, dtype=video.dtype),
                       video[:, :, -steps:]):
            return (latent, "%s [tail only: %d frames / %d steps; unchanged]"
                    % (report, frames, steps))
        output_video = video.clone()
        output_video[:, :, -steps:] = refined_video.to(video.device, dtype=video.dtype)
        out = dict(latent)
        out["samples"] = comfy.nested_tensor.NestedTensor((output_video, audio))
        return (out, "%s [tail only: %d frames / %d steps]"
                % (report, frames, steps))
