"""Reference compression/refinement adapted from Fantastic H3 RefMod Stack (MIT).
See LICENSES/Fantastic-RefMod-MIT.txt and LICENSES/MiniMaxH3Mod-MIT.txt.
Only the reference latent is optimized; VAEs and diffusion models are not trained.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchaudio
import comfy.utils
import comfy.model_management as mm

def resize_ref(image, short_edge):
    """Aspect-preserving downscale (never up) to `short_edge`, dims to /32 —
    what the native reference node does before encoding."""
    h, w = (image.shape[1], image.shape[2])
    if h <= 0 or w <= 0:
        raise ValueError(f'reference has an empty frame ({h}x{w})')
    scale = min(1.0, short_edge / min(h, w))
    tw = max(32, round(w * scale / 32) * 32)
    th = max(32, round(h * scale / 32) * 32)
    samples = image[..., :3].movedim(-1, 1)
    samples = comfy.utils.common_upscale(samples, tw, th, 'lanczos', 'disabled')
    return samples.movedim(1, -1)

def ensure_min_size(image, floor=320):
    """The H3 VAE tiles at ~256px; a smaller edge makes a zero-size tile."""
    h, w = (image.shape[1], image.shape[2])
    if h >= floor and w >= floor:
        return image
    scale = floor / min(h, w)
    tw = max(floor, round(w * scale / 32) * 32)
    th = max(floor, round(h * scale / 32) * 32)
    samples = image[..., :3].movedim(-1, 1)
    samples = comfy.utils.common_upscale(samples, tw, th, 'lanczos', 'disabled')
    return samples.movedim(1, -1)

def snap_to_h3_grid(n):
    """Frames the H3 video VAE encodes whole: it works in chunks of 17 and
    stores 2 latent frames for the first chunk, then 5 more per chunk, so a
    clip is cut to 5, 22, 39, 56… frames (the same rule core's Reference to
    Video applies). Fewer than 5 frames are taken as they are."""
    if n <= 1:
        return 1
    if n < 5:
        return n
    return n - (n - 5) % 17

def aspect_grid(long_edge, aspect):
    """Even pool grid whose long edge is the dial and whose short edge
    follows the source aspect (h/w), so a portrait is not squashed square."""
    if aspect >= 1.0:
        h, w = (long_edge, long_edge / aspect)
    else:
        w, h = (long_edge, long_edge * aspect)
    return (max(2, round(h / 2) * 2), max(2, round(w / 2) * 2))

def pool_latent(z, t, h, w):
    if z.shape[2] == t and z.shape[3] == h and (z.shape[4] == w):
        return z
    return F.adaptive_avg_pool3d(z.float(), (t, h, w)).to(z.dtype)

def optimize_latent(z_small, z_full, steps=150, lr=0.02, progress=None):
    """Refine the pooled latent so its trilinear upsample matches the full
    encode. Only the small latent is trainable; no diffusion model."""
    if steps <= 0:
        return z_small
    device = z_full.device
    with torch.inference_mode(False), torch.set_grad_enabled(True):
        target = z_full.clone().float().to(device)
        param = nn.Parameter(z_small.clone().float().to(device))
        opt = torch.optim.Adam([param], lr=lr)
        size = tuple(target.shape[2:])
        for i in range(steps):
            if i % 25 == 0:
                mm.throw_exception_if_processing_interrupted()
            opt.zero_grad()
            up = F.interpolate(param, size=size, mode='trilinear', align_corners=False)
            F.mse_loss(up, target).backward()
            opt.step()
            if progress and (i + 1) % 50 == 0:
                progress(i + 1, steps)
        refined = param.detach().to(z_small.dtype)
    return refined

def _cover(image, tw, th):
    """Scale and centre-crop to exactly tw x th."""
    samples = image[..., :3].movedim(-1, 1)
    samples = comfy.utils.common_upscale(samples, tw, th, 'lanczos', 'center')
    return samples.movedim(1, -1)

def encode_look(vae, sources, *, mode, ref_resolution, grid, latent_frames, steps, label, progress=None):
    """One latent from one or more sources, stacked along time.

    `sources` is [(frames [N,H,W,3], is_video)]. Each is encoded on its own
    and the results are joined, one latent frame per picture and a short
    sequence per clip. They must share a frame size, so the first source
    sets it: Full cover-crops the others to its canvas, Compressed pools
    every one to a grid shaped like it — the same rules as
    ComfyUI-MiniMaxH3Mod's Create node."""
    if not sources:
        raise ValueError('no pictures or clips to encode')
    for frames, _v in sources:
        if frames.ndim != 4 or frames.shape[-1] < 3:
            raise ValueError(f'{label}: expected an IMAGE batch, got {tuple(frames.shape)}')
    h0, w0 = (sources[0][0].shape[1], sources[0][0].shape[2])
    canvas = None
    if mode == 'encode' and len(sources) > 1:
        scale = min(1.0, ref_resolution / min(h0, w0))
        canvas = (max(32, round(w0 * scale / 32) * 32), max(32, round(h0 * scale / 32) * 32))
    gh, gw = aspect_grid(grid, h0 / w0)
    parts, shapes, notes, first_frame = ([], [], [], None)
    n = len(sources)
    for i, (src, is_video) in enumerate(sources):
        src = src if is_video else src[:1]
        if is_video:
            src = src[:snap_to_h3_grid(min(latent_frames, src.shape[0]))]
        src = _cover(src, *canvas) if canvas else resize_ref(src, ref_resolution)
        src = ensure_min_size(src)
        if first_frame is None:
            first_frame = src[0].detach().cpu()
        mm.throw_exception_if_processing_interrupted()
        z = vae.encode(src)
        if z.dim() != 5 or z.shape[1] != 24:
            raise ValueError(f'Expected an H3 video latent [1,24,T,H,W], got {tuple(z.shape)}; the connected VAE is not the H3 video VAE.')
        shapes.append(f'{z.shape[2]}x{z.shape[3]}x{z.shape[4]}')
        if mode == 'encode':
            part = z.to(torch.float16)
        else:
            part = pool_latent(z, z.shape[2] if is_video else 1, gh, gw).to(torch.float16)
            if steps > 0:
                part = optimize_latent(part, z.float(), steps=steps, progress=(lambda k, m, i=i: progress((i + k / m) / n)) if progress else None)
        parts.append(part.cpu())
        if progress:
            progress((i + 1) / n)
    latent = torch.cat(parts, dim=2).contiguous()
    if len(sources) > 1:
        notes.append(f'stacked {len(sources)} sources into {latent.shape[2]} frames')
    info = {'source_shape': ' +'.join(shapes), 'pool': '' if mode == 'encode' else f'{latent.shape[2]}x{gh}x{gw}', 'notes': notes, 'first_frame': first_frame}
    return (latent, info)

def join_audio(clips):
    """Several AUDIO dicts -> one, in order, as 32 kHz stereo."""
    parts = []
    for a in clips:
        w, sr = (a['waveform'], int(a['sample_rate']))
        if w.ndim != 3 or w.shape[0] != 1 or w.shape[1] not in (1, 2) or (sr <= 0) or (w.shape[-1] < 1):
            raise ValueError('Audio must be one batch of mono or stereo samples.')
        if w.shape[1] == 1:
            w = w.repeat(1, 2, 1)
        if sr != 32000:
            w = torchaudio.functional.resample(w, sr, 32000)
        parts.append(w.float())
    return {'waveform': torch.cat(parts, dim=-1), 'sample_rate': 32000}
