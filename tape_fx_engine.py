# MIT License
# 
# Copyright (c) 2026 Analog Tape FX contributors
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
MiniMax-H3-Tape-FX for ComfyUI -- VHS / BetaMax / LaserDisc tape effects
========================================================================

A single mega-node that degrades images (and video batches) with authentic
analog-tape playback artifacts:

  * Format DNA        -- VHS softness, BetaMax sharpness, LaserDisc clarity
  * Tracking error bands, signal dropout, tape creases, frame ghosting,
    head-switching noise and vertical hold roll
  * Worn-section simulation -- damage spikes inside a configurable frame range
  * Authentic VCR on-screen display (PLAY / REC / tape counter / date stamp)
  * Damage presets (mint -> destroyed) combined with full manual control

The batch dimension of the IMAGE input is treated as a timeline, so temporal
effects (tracking bands, rolls, ghosting, counter, blinking REC) animate
correctly on video output (AnimateDiff, video latent batches, ...).

No dependencies beyond what ComfyUI already ships: torch + numpy.
Same seed -> same result on every machine.
"""

import math

import numpy as np
import torch
import torch.nn.functional as F

__version__ = "1.0.0"

# --------------------------------------------------------------------------
# 5x7 pixel font for the VCR on-screen display
# --------------------------------------------------------------------------

_FONT_RAW = {
    "A": ".XXX./X...X/X...X/XXXXX/X...X/X...X/X...X",
    "B": "XXXX./X...X/X...X/XXXX./X...X/X...X/XXXX.",
    "C": ".XXXX/X..../X..../X..../X..../X..../.XXXX",
    "D": "XXXX./X...X/X...X/X...X/X...X/X...X/XXXX.",
    "E": "XXXXX/X..../X..../XXXX./X..../X..../XXXXX",
    "F": "XXXXX/X..../X..../XXXX./X..../X..../X....",
    "G": ".XXXX/X..../X..../X..XX/X...X/X...X/.XXXX",
    "H": "X...X/X...X/X...X/XXXXX/X...X/X...X/X...X",
    "I": "XXXXX/..X../..X../..X../..X../..X../XXXXX",
    "J": "..XXX/...X./...X./...X./...X./X..X./.XX..",
    "K": "X...X/X..X./X.X../XX.../X.X../X..X./X...X",
    "L": "X..../X..../X..../X..../X..../X..../XXXXX",
    "M": "X...X/XX.XX/X.X.X/X.X.X/X...X/X...X/X...X",
    "N": "X...X/XX..X/X.X.X/X..XX/X...X/X...X/X...X",
    "O": ".XXX./X...X/X...X/X...X/X...X/X...X/.XXX.",
    "P": "XXXX./X...X/X...X/XXXX./X..../X..../X....",
    "Q": ".XXX./X...X/X...X/X...X/X.X.X/X..X./.XX.X",
    "R": "XXXX./X...X/X...X/XXXX./X.X../X..X./X...X",
    "S": ".XXXX/X..../X..../.XXX./....X/....X/XXXX.",
    "T": "XXXXX/..X../..X../..X../..X../..X../..X..",
    "U": "X...X/X...X/X...X/X...X/X...X/X...X/.XXX.",
    "V": "X...X/X...X/X...X/X...X/X...X/.X.X./..X..",
    "W": "X...X/X...X/X...X/X.X.X/X.X.X/XX.XX/X...X",
    "X": "X...X/X...X/.X.X./..X../.X.X./X...X/X...X",
    "Y": "X...X/X...X/.X.X./..X../..X../..X../..X..",
    "Z": "XXXXX/....X/...X./..X../.X.../X..../XXXXX",
    "0": ".XXX./X...X/X..XX/X.X.X/XX..X/X...X/.XXX.",
    "1": "..X../.XX../..X../..X../..X../..X../XXXXX",
    "2": ".XXX./X...X/....X/...X./..X../.X.../XXXXX",
    "3": "XXXX./....X/....X/.XXX./....X/....X/XXXX.",
    "4": "...X./..XX./.X.X./X..X./XXXXX/...X./...X.",
    "5": "XXXXX/X..../XXXX./....X/....X/X...X/.XXX.",
    "6": ".XXX./X..../X..../XXXX./X...X/X...X/.XXX.",
    "7": "XXXXX/....X/...X./..X../.X.../.X.../.X...",
    "8": ".XXX./X...X/X...X/.XXX./X...X/X...X/.XXX.",
    "9": ".XXX./X...X/X...X/.XXXX/....X/....X/.XXX.",
    ":": "...../..X../..X../...../..X../..X../.....",
    ".": "...../...../...../...../...../.XX../.XX..",
    "-": "...../...../...../XXXXX/...../...../.....",
    "/": "...../....X/...X./..X../.X.../X..../.....",
    "'": "..X../..X../...../...../...../...../.....",
    "(": "...X./..X../.X.../.X.../.X.../..X../...X.",
    ")": ".X.../..X../...X./...X./...X./..X../.X...",
    " ": "...../...../...../...../...../...../.....",
    # playback / record symbols
    "\u25b6": "X..../XX.../XXX../XXXX./XXX../XX.../X....",   # play triangle
    "\u25cf": "...../.XXX./XXXXX/XXXXX/XXXXX/.XXX./.....",   # rec dot
}


def _build_font():
    font = {}
    for ch, rows in _FONT_RAW.items():
        font[ch] = [row.ljust(5, ".") for row in rows.split("/")]
    return font


FONT = _build_font()

# --------------------------------------------------------------------------
# Format DNA -- how each dead format actually behaves
# --------------------------------------------------------------------------

FORMAT_PROFILES = {
    "vhs": {
        "label": "VHS",
        "luma_blur": 1.15,       # ~240 usable lines, soft luma
        "chroma_bleed": 1.00,    # very low chroma bandwidth
        "chroma_gain": 1.06,
        "noise": 1.00,
        "flicker": 1.00,
        "dropout_mode": "streak",   # long white horizontal streaks
        "dropout_amount": 1.00,
        "head_switch": 1.00,     # real VHS head-switching noise
        "tracking": 1.00,
        "creases": 1.00,         # it is tape, it creases
        "vertical_roll": 1.00,
        "ghost": 0.90,
        "ghost_shift": 3,        # px (scaled with resolution)
        "black_lift": 1.00,
    },
    "betamax": {
        "label": "BetaMax",
        "luma_blur": 0.62,       # sharper than VHS (~260-280 lines)
        "chroma_bleed": 0.65,
        "chroma_gain": 1.04,
        "noise": 0.80,
        "flicker": 0.85,
        "dropout_mode": "streak",
        "dropout_amount": 0.80,  # shorter streaks, better SNR
        "head_switch": 1.00,
        "tracking": 0.65,        # Beta tracked better
        "creases": 0.70,
        "vertical_roll": 0.70,
        "ghost": 0.60,
        "ghost_shift": 2,
        "black_lift": 0.80,
    },
    "laserdisc": {
        "label": "LaserDisc",
        "luma_blur": 0.32,       # ~420 lines, sharpest analog video
        "chroma_bleed": 0.35,
        "chroma_gain": 1.02,
        "noise": 0.55,
        "flicker": 0.50,
        "dropout_mode": "speckle",  # "laser rot" sparklies
        "dropout_amount": 1.20,
        "head_switch": 0.0,      # no tape transport, no head switch
        "tracking": 0.35,        # mild timebase jitter instead
        "creases": 0.0,          # optical disc: nothing to crease
        "vertical_roll": 0.90,   # disc timebase errors do roll
        "ghost": 1.35,           # crosstalk ghosting (disc other side)
        "ghost_shift": 6,
        "black_lift": 0.40,
    },
}

# Preset = global damage multiplier applied on top of the damage sliders.
# The "look" sliders (softness / bleed / scanlines) are NOT scaled, because
# even a mint VHS tape is still soft.
PRESET_MULT = {
    "worn_out": 1.00,
    "lightly_worn": 0.40,
    "mint": 0.08,
    "destroyed": 1.90,
    "custom": 1.00,
}

OSD_COLORS = {
    "white": (1.00, 1.00, 1.00),
    "teal": (0.38, 0.95, 0.86),
    "amber": (1.00, 0.72, 0.25),
}

# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

_KCACHE = {}


def _gauss_kernel(sigma, device):
    key = (round(float(sigma), 3), str(device))
    if key not in _KCACHE:
        r = max(1, int(math.ceil(3.0 * sigma)))
        x = torch.arange(-r, r + 1, dtype=torch.float32)
        k = torch.exp(-(x * x) / (2.0 * sigma * sigma + 1e-8))
        _KCACHE[key] = (k / k.sum()).to(device)
    return _KCACHE[key]


def _blur_sep(img, sigma, device):
    """Separable gaussian blur on a (H, W) tensor."""
    if sigma < 0.25:
        return img
    k = _gauss_kernel(sigma, device)
    r = len(k) // 2
    x = img[None, None]
    x = F.conv2d(x, k.view(1, 1, 1, -1), padding=(0, r))
    x = F.conv2d(x, k.view(1, 1, -1, 1), padding=(r, 0))
    return x[0, 0]


def _shift_x(img, px, device):
    """Shift a (H, W) tensor horizontally by integer px (replicate edges)."""
    px = int(round(px))
    if px == 0:
        return img
    w = img.shape[-1]
    if px > 0:
        return F.pad(img, (px, 0), mode="replicate")[:, :w]
    n = -px
    return F.pad(img, (0, n), mode="replicate")[:, n:]


def _to_ycc(img):
    """RGB (3,H,W) -> (Y, Cb, Cr), full-range BT.601-ish."""
    r, g, b = img[0], img[1], img[2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = (b - y) / 1.772
    cr = (r - y) / 1.402
    return y, cb, cr


def _from_ycc(y, cb, cr):
    r = y + 1.402 * cr
    b = y + 1.772 * cb
    g = (y - 0.299 * r - 0.114 * b) / 0.587
    return torch.stack((r, g, b), dim=0)


def _warp(img, dx, dy):
    """Bilinear warp of a (C,H,W) tensor by pixel displacement fields (H,W)."""
    _, h, w = img.shape
    device = img.device
    ys, xs = torch.meshgrid(
        torch.arange(h, dtype=torch.float32, device=device),
        torch.arange(w, dtype=torch.float32, device=device),
        indexing="ij",
    )
    gx = ((xs + dx) / max(1, w - 1)) * 2.0 - 1.0
    gy = ((ys + dy) / max(1, h - 1)) * 2.0 - 1.0
    grid = torch.stack((gx, gy), dim=-1)[None]
    return F.grid_sample(
        img[None], grid, mode="bilinear", padding_mode="border", align_corners=True
    )[0]


def _wear_mask(n, start, end, fade=4):
    """Per-frame 0..1 mask: 1 inside frames [start, end), smooth 4-frame ramps."""
    w = np.zeros(n, dtype=np.float64)
    try:
        a, b = int(start), int(end)
    except (TypeError, ValueError):
        return w
    if b <= a:
        return w
    a, b = max(0, a), min(n, b)
    if b <= a:
        return w
    w[a:b] = 1.0
    f = max(1, int(fade))
    for k in range(1, f + 1):
        v = 1.0 - k / (f + 1.0)
        if a - k >= 0:
            w[a - k] = max(w[a - k], v)
        if b - 1 + k < n:
            w[b - 1 + k] = max(w[b - 1 + k], v)
    return w


# --------------------------------------------------------------------------
# Damage event schedule (built once per run, seeded -> reproducible)
# --------------------------------------------------------------------------

def _build_schedule(n, seed, s_track, s_roll, s_crease):
    """Per-frame event lists + smooth noise arrays for the whole batch."""
    rng = np.random.default_rng(int(seed))

    # ---- tracking error bands -------------------------------------------
    tracking = [[] for _ in range(n)]
    live = []

    def _new_track_event(i):
        return dict(
            y=float(rng.uniform(0.05, 0.88)),
            hh=float(rng.uniform(0.05, 0.16)) * (0.7 + 0.6 * s_track[i]),
            drift=float(rng.uniform(-0.008, 0.008)),
            off=float(rng.uniform(0.4, 1.0)),
            wave=float(rng.uniform(0.1, 1.0)),
            freq=float(rng.uniform(0.4, 2.2)),
            phase=float(rng.uniform(0.0, 6.28318)),
            s=float(rng.uniform(0.55, 1.0)),
            left=int(rng.integers(2, 11)),
        )

    # A worn tape should show its damage immediately: guarantee a tracking
    # band on frame 0 whenever tracking is dialed in, so single stills
    # (the most common case) always reveal the effect.
    if n > 0 and s_track[0] > 0.15:
        ev = _new_track_event(0)
        ev["s"] = float(rng.uniform(0.65, 1.0))
        live.append(ev)

    for i in range(n):
        p = float(np.clip(0.02 + 0.40 * s_track[i], 0.0, 0.85))
        for _ in range(2):
            if len(live) < 3 and rng.random() < p:
                live.append(_new_track_event(i))
        for ev in live:
            tracking[i].append(dict(ev))
        for ev in live:
            ev["y"] = float(np.clip(ev["y"] + ev["drift"], 0.0, 0.92))
            ev["left"] -= 1
        live = [e for e in live if e["left"] > 0]

    # ---- vertical hold rolls --------------------------------------------
    roll = [[] for _ in range(n)]
    live = []
    for i in range(n):
        p = float(np.clip(0.004 + 0.10 * s_roll[i], 0.0, 0.45))
        if not live and rng.random() < p:
            live.append(
                dict(
                    off=float(rng.uniform(0.0, 0.15)),
                    speed=float(rng.uniform(0.05, 0.16)) * (0.5 + 0.9 * s_roll[i]),
                    s=float(rng.uniform(0.55, 1.0)),
                    dir=float(rng.choice((-1.0, 1.0))),
                    left=int(rng.integers(3, 15)),
                )
            )
        if live:
            ev = live[0]
            roll[i].append(dict(ev))
            ev["off"] += ev["speed"]
            ev["left"] -= 1
            if ev["left"] <= 0:
                live = []

    # ---- tape creases (persist -- they are physical damage) --------------
    crease = [[] for _ in range(n)]
    live = []

    def _new_crease_event():
        return dict(
            px=float(rng.uniform(0.15, 0.85)),
            py=float(rng.uniform(0.10, 0.90)),
            theta=float(rng.uniform(0.25, 1.1)) * float(rng.choice((-1.0, 1.0))),
            width=float(rng.uniform(0.004, 0.010)) * (0.7 + 0.8 * s_crease[0]),
            amp=float(rng.uniform(0.5, 1.0)),
            s=float(rng.uniform(0.5, 1.0)),
            left=int(rng.integers(10, 70)),
        )

    # Guarantee a visible crease on frame 0 for heavily damaged tapes.
    if n > 0 and s_crease[0] > 0.25:
        live.append(_new_crease_event())

    for i in range(n):
        p = float(np.clip(0.008 + 0.15 * s_crease[i], 0.0, 0.5))
        if len(live) < 2 and rng.random() < p:
            live.append(_new_crease_event())
        for ev in live:
            crease[i].append(dict(ev))
        for ev in live:
            ev["left"] -= 1
        live = [e for e in live if e["left"] > 0]

    # ---- smooth noise: vertical jitter + luminance flicker ---------------
    if n > 1:
        walk = np.cumsum(rng.normal(0.0, 0.30, n))
        jit = walk - np.linspace(walk[0], walk[-1], n)
        walk = np.cumsum(rng.normal(0.0, 0.22, n))
        flk = walk - np.linspace(walk[0], walk[-1], n)
    else:
        jit = np.zeros(1)
        flk = np.zeros(1)
    jit = np.clip(jit * 0.7 + rng.normal(0.0, 0.25, n) * 0.3, -2.0, 2.0)
    flk = np.clip(flk * 0.7 + rng.normal(0.0, 0.30, n) * 0.3, -1.2, 1.2)

    return {"tracking": tracking, "roll": roll, "crease": crease, "jit": jit, "flk": flk}


# --------------------------------------------------------------------------
# OSD (on-screen display) rendering
# --------------------------------------------------------------------------

def _text_bitmap(text, scale):
    """Render text with the 5x7 pixel font -> float32 (h, w) bitmap."""
    glyphs = [FONT.get(ch, FONT[" "]) for ch in str(text).upper()]
    cw = 6 * scale
    width = max(1, len(glyphs) * cw - scale)
    height = 7 * scale
    bmp = np.zeros((height, width), dtype=np.float32)
    for gi, rows in enumerate(glyphs):
        cell = np.zeros((7, 5), dtype=np.float32)
        for ri, row in enumerate(rows):
            for ci, ch in enumerate(row):
                if ch == "X":
                    cell[ri, ci] = 1.0
        cell = np.kron(cell, np.ones((scale, scale), dtype=np.float32))
        x0 = gi * cw
        bmp[:, x0 : x0 + 5 * scale] = cell
    return bmp


def _stamp(img, bmp, x, y, color, device):
    """Alpha-composite a bitmap onto a (3,H,W) image at (x, y) (clipped)."""
    _, h, w = img.shape
    bh, bw = bmp.shape
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(w, x + bw), min(h, y + bh)
    if x1 <= x0 or y1 <= y0:
        return
    a = torch.from_numpy(bmp[y0 - y : y1 - y, x0 - x : x1 - x]).to(device)[None]
    img[:, y0:y1, x0:x1] = img[:, y0:y1, x0:x1] * (1.0 - a) + color[:, None, None] * a


def _draw_text(img, text, x, y, rgb, scale, cache, device):
    if not str(text):
        return
    key = (str(text), scale)
    if key not in cache:
        cache[key] = _text_bitmap(text, scale)
    bmp = cache[key]
    sh = max(1, scale)
    _stamp(img, bmp, x + sh, y + sh, torch.zeros(3, device=device), device)
    _stamp(img, bmp, x, y, rgb, device)


def _draw_osd(img, i, ctx):
    """Draw the VCR on-screen display on a (3,H,W) frame."""
    device = img.device
    _, h, w = img.shape
    scale = max(1, int(ctx["osd_scale"]))
    margin = max(4, int(h * 0.035))
    rgb = torch.tensor(ctx["osd_rgb"], dtype=torch.float32, device=device)
    cache = ctx["osd_cache"]
    fps = max(1, int(ctx["osd_fps"]))

    # status: PLAY or blinking REC, top-left
    if ctx["osd_mode"] == "play":
        _draw_text(img, "\u25b6 PLAY", margin, margin, rgb, scale, cache, device)
    elif ctx["osd_mode"] == "rec":
        if (i / fps) % 1.0 < 0.70:
            _draw_text(img, "\u25cf REC", margin, margin, rgb, scale, cache, device)

    # tape counter, top-right (h:mm:ss)
    if ctx["osd_counter"]:
        secs = int(ctx["osd_counter_start"]) + i // fps
        secs = max(0, secs)
        text = "{}:{:02d}:{:02d}".format(secs // 3600, (secs % 3600) // 60, secs % 60)
        bmp = _text_bitmap(text, scale)
        _draw_text(
            img, text, w - margin - bmp.shape[1], margin, rgb, scale, cache, device
        )

    # custom stamp (date etc.), bottom-right
    if ctx["osd_custom"]:
        bmp = _text_bitmap(ctx["osd_custom"], scale)
        _draw_text(
            img,
            ctx["osd_custom"],
            w - margin - bmp.shape[1],
            h - margin - bmp.shape[0],
            rgb,
            scale,
            cache,
            device,
        )
    return img


# --------------------------------------------------------------------------
# Per-frame pipeline
# --------------------------------------------------------------------------

def _process_frame(img, i, ctx):
    """Apply the full analog-tape pipeline to one (3,H,W) frame."""
    device = img.device
    _, h, w = img.shape
    sf = ctx["sf"]
    prof = ctx["prof"]

    s_track = float(ctx["s_track"][i])
    s_drop = float(ctx["s_drop"][i])
    s_crease = float(ctx["s_crease"][i])
    s_ghost = float(ctx["s_ghost"][i])
    s_head = float(ctx["s_head"][i])
    s_roll = float(ctx["s_roll"][i])
    s_noise = float(ctx["s_noise"][i])
    s_flick = float(ctx["s_flick"][i])

    gen = torch.Generator()
    gen.manual_seed(ctx["frame_seed"](i))

    def rnd(*shape):
        return torch.randn(*shape, generator=gen).to(device)

    def uni(*shape):
        return torch.rand(*shape, generator=gen).to(device)

    # ---- stage A: analog colour / bandwidth (YCbCr space) ----------------
    y, cb, cr = _to_ycc(img)
    y = _blur_sep(y, ctx["luma_sigma"], device)
    cb = _shift_x(_blur_sep(cb, ctx["chroma_sigma"], device), ctx["chroma_shift"], device)
    cr = _shift_x(_blur_sep(cr, ctx["chroma_sigma"], device), ctx["chroma_shift"], device)
    gain = ctx["chroma_gain"]
    cb, cr = cb * gain, cr * gain
    if s_noise > 0.005:
        y = y + rnd(h, w) * (0.012 + 0.10 * s_noise)
        cn = (0.010 + 0.060 * s_noise) * prof["chroma_bleed"]
        cb = cb + rnd(h, w) * cn
        cr = cr + rnd(h, w) * cn
    img = _from_ycc(y, cb, cr)

    # ---- stage B: transport damage ---------------------------------------
    # vertical roll (big sync loss) vs small vertical jitter
    roll_events = ctx["schedule"]["roll"][i]
    vshift = 0.0
    rolled = False
    if roll_events:
        ev = roll_events[0]
        s = s_roll * float(ev["s"])
        if s > 0.30:
            rolled = True
            shift = int(ev["off"] * h) % h
            d = int(ev["dir"])
            if shift:
                img = torch.roll(img, shifts=-shift * d, dims=1)
            # the tear sits where wrapped rows meet: bottom entry point for
            # upward rolls, top entry point for downward ones
            bar_y = shift if d < 0 else (h - shift) % h
            hb = max(2, int(h * (0.02 + 0.10 * min(1.0, s))))
            y1 = min(h, bar_y + hb)
            if y1 > bar_y:
                bar = rnd(y1 - bar_y, w)
                img[:, bar_y:y1, :] = 0.08 + bar[None] * 0.20
            if bar_y > 0:
                img[:, bar_y - 1 : bar_y, :] += 0.35 * min(1.0, s)
            img = img + rnd(3, h, w) * 0.03 * min(1.0, s)
    if not rolled and s_roll > 0.005:
        vshift = sf * (0.4 + 3.0 * s_roll) * float(ctx["schedule"]["jit"][i])

    # ---- warp displacement field ------------------------------------------
    dx = torch.zeros(h, w, device=device)
    dy = torch.zeros(h, w, device=device)
    if abs(vshift) > 0.05:
        dy = dy + vshift

    band_info = []
    for ev in ctx["schedule"]["tracking"][i]:
        s = s_track * float(ev["s"])
        if s <= 0.01:
            continue
        y0 = int(ev["y"] * h)
        y1 = min(h, y0 + max(3, int(ev["hh"] * h)))
        hh = y1 - y0
        if hh <= 1:
            continue
        env = torch.from_numpy(
            0.5 - 0.5 * np.cos(np.pi * np.linspace(0.0, 1.0, hh))
        ).float().to(device)
        base = w * (0.015 + 0.12 * s) * float(ev["off"])
        rown = rnd(hh) * (2.0 + 12.0 * s) * sf
        ramp = torch.linspace(-1.0, 1.0, hh, device=device) * base
        xs_row = torch.arange(w, device=device, dtype=torch.float32)
        wave = (
            torch.sin(6.28318 * float(ev["freq"]) * xs_row / w + float(ev["phase"]))
            * w
            * 0.022
            * s
            * float(ev["wave"])
        )
        dx[y0:y1, :] += (ramp[:, None] + rown[:, None] + wave[None, :]) * env[:, None]
        band_info.append((y0, y1, env, s))

    crease_info = []
    for ev in ctx["schedule"]["crease"][i]:
        s = s_crease * float(ev["s"])
        if s <= 0.01:
            continue
        key = (
            round(ev["px"], 4),
            round(ev["py"], 4),
            round(ev["theta"], 4),
            round(ev["width"], 5),
        )
        cached = ctx["crease_cache"].get(key)
        if cached is None:
            ys, xs = torch.meshgrid(
                torch.arange(h, dtype=torch.float32, device=device),
                torch.arange(w, dtype=torch.float32, device=device),
                indexing="ij",
            )
            ct, st = math.cos(ev["theta"]), math.sin(ev["theta"])
            d = (ys - h * ev["py"]) * ct - (xs - w * ev["px"]) * st
            wpx = max(2.0, w * float(ev["width"]))
            m = torch.exp(-(d * d) / (wpx * wpx))
            cached = (m, torch.sign(d))
            ctx["crease_cache"][key] = cached
        m, side = cached
        dx = dx + sf * (3.0 + 14.0 * s) * float(ev["amp"]) * side * m
        crease_info.append((m, s))

    if s_head > 0.012:
        hs = max(3, int(h * 0.022))
        offs = (rnd(hs) * 2.0 - 1.0) * (8.0 + 50.0 * s_head) * sf
        dx[h - hs :, :] = dx[h - hs :, :] + offs[:, None]

    need_warp = (
        abs(vshift) > 0.3
        or bool(band_info)
        or bool(crease_info)
        or s_head > 0.012
    )
    if need_warp:
        img = _warp(img, dx, dy)

    # ---- band post-effects (noise, lost lines, bright edge) ----------------
    for y0, y1, env, s in band_info:
        hh = y1 - y0
        s = min(1.4, s)
        n = rnd(1, hh, w)[0] * (0.08 + 0.22 * s) * env[:, None]
        img[:, y0:y1, :] = img[:, y0:y1, :] + n[None]
        img[:, y0 : min(y0 + 2, y1), :] = (
            img[:, y0 : min(y0 + 2, y1), :] + 0.32 * s
        )
        if s > 0.55:
            lost = uni(hh) < (0.35 * (s - 0.55) / 0.45)
            idx = torch.nonzero(lost).flatten().tolist()
            for r in idx:
                img[:, y0 + r, :] = 0.35 + 0.35 * rnd(1, w)[0]

    # ---- crease post-effects (bright kink + crackle) ------------------------
    for m, s in crease_info:
        k = float(min(1.0, s))
        a = (0.5 * k * m)[None]
        img = img * (1.0 - a) + (img * 0.5 + 0.55) * a
        img = img + (rnd(1, h, w)[0] * 0.12 * k)[None] * m[None]

    # ---- head-switch bar post-effects ---------------------------------------
    if s_head > 0.012:
        hs = max(3, int(h * 0.022))
        img[:, h - hs :, :] = img[:, h - hs :, :] + (rnd(1, hs, w)[0] * 0.26 * s_head)[None]
        img[:, h - hs :, :] = img[:, h - hs :, :] * (1.0 - 0.15 * s_head)
        if s_head > 0.35:
            img[:, -2:, :] = 0.30 + 0.45 * rnd(1, 2, w)[0]

    # ---- signal dropout -------------------------------------------------------
    if s_drop > 0.01:
        if prof["dropout_mode"] == "streak":
            # VHS oxide loss: thin bright streaks of varying length
            p = 0.00002 + 0.0009 * s_drop
            lmax = max(8.0, (6 + 26 * sf) * (0.40 + 0.60 * s_drop))
            hmax = max(1, round(1.5 * sf))
        else:
            # laserdisc rot: tiny bright sparklies
            p = 0.0001 + 0.0025 * s_drop
            lmax = max(2.0, 1.6 * sf)
            hmax = max(1, round(1.2 * sf))
        # dropout defects persist ~2 frames: same spot on the tape, two fields
        gd = torch.Generator()
        gd.manual_seed(ctx["drop_seed"](i))
        seeds = torch.rand(h, w, generator=gd) < p
        idx = torch.nonzero(seeds).tolist()
        if idx:
            rr = torch.rand(len(idx) * 3, generator=gd).tolist()
        else:
            rr = []
        frame_op = (0.55 + 0.45 * s_drop) * (0.70 + 0.30 * float(torch.rand(1, generator=gd)))
        white_v = 0.92 + 0.08 * float(torch.rand(1, generator=gd))
        mask = torch.zeros(h, w, device=device)
        for k, (sy, sx) in enumerate(idx):
            u = rr[3 * k] ** 2  # skew toward short streaks
            if prof["dropout_mode"] == "streak":
                L = max(2, int(lmax * (0.15 + 0.85 * u)))
                Hh = max(1, min(hmax, round(hmax * (0.6 + 0.8 * rr[3 * k + 1]))))
            else:
                L = max(1, int(lmax * (0.5 + 0.5 * rr[3 * k])))
                Hh = max(1, int(hmax * (0.6 + 0.8 * rr[3 * k + 1])))
            x0 = max(0, sx - L // 2)
            x1 = min(w, x0 + L)
            y1 = min(h, sy + Hh)
            if x1 <= x0 or sy >= h:
                continue
            a = frame_op * (0.80 + 0.20 * rr[3 * k + 2])
            if rr[3 * k + 2] < 0.06:
                img[:, sy:y1, x0:x1] = img[:, sy:y1, x0:x1] * 0.15  # black dropout
            else:
                mask[sy:y1, x0:x1] = torch.clamp(mask[sy:y1, x0:x1] + a, max=1.0)
        # soften streak edges for an analog rolloff
        mask = _blur_sep(mask, max(0.5, 0.35 * sf), device)
        img = img * (1.0 - mask[None]) + white_v * mask[None]

    # ---- ghosting / crosstalk --------------------------------------------------
    if s_ghost > 0.01 and i > 0:
        gs = int(max(1, round(prof["ghost_shift"] * sf)))
        gh = F.pad(ctx["prev"], (gs, 0), mode="replicate")[:, :, :w]
        a = 0.45 * s_ghost
        img = img * (1.0 - a) + gh * a
    ctx["prev"] = img.clone()

    # ---- stage C: levels, flicker, scanlines -----------------------------------
    if s_flick > 0.01:
        g = 1.0 + s_flick * 0.07 * float(ctx["schedule"]["flk"][i])
        img = img * g
    lift = min(0.09, (0.015 + 0.055 * float(ctx["dmg"][i])) * prof["black_lift"])
    img = img * (1.0 - lift) + lift * 0.5
    if ctx["scan"] > 0.01:
        a = 0.09 * ctx["scan"]
        img = img * (1.0 - a)
        img[:, 1::2, :] = img[:, 1::2, :] * (1.0 - a)

    img = img.clamp(0.0, 1.0)

    # ---- stage D: on-screen display ---------------------------------------------
    if ctx["osd"]:
        img = _draw_osd(img, i, ctx)

    return img


# --------------------------------------------------------------------------
# The node
# --------------------------------------------------------------------------

class TapeEngine:
    """VHS / BetaMax / LaserDisc worn-tape effects in a single node."""

    CATEGORY = "MiniMax-H3-Tape-FX"
    DESCRIPTION = (
        "Degrade images and video batches with authentic analog-tape artifacts: "
        "VHS / BetaMax / LaserDisc looks, tracking errors, dropout, creases, "
        "ghosting, head-switch noise, vertical roll, worn tape sections and a "
        "VCR on-screen display. The batch dimension is the timeline."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "Input image or video batch (batch = timeline)"}),
                "format": (
                    ["vhs", "betamax", "laserdisc"],
                    {"tooltip": "Tape format DNA: VHS is soft and noisy, BetaMax sharper and steadier, LaserDisc clean but prone to rot speckle and crosstalk"},
                ),
                "preset": (
                    ["worn_out", "lightly_worn", "mint", "destroyed", "custom"],
                    {"tooltip": "Global damage level. Scales all damage sliders; the look sliders (softness/bleed/scanlines) are unaffected. 'custom' uses the sliders exactly as set"},
                ),
                "tracking": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01,
                                       "tooltip": "Tracking error bands: horizontal tearing waves that crawl over the image"}),
                "dropout": ("FLOAT", {"default": 0.30, "min": 0.0, "max": 1.0, "step": 0.01,
                                      "tooltip": "Signal dropout: white streaks (tape) or rot speckles (LaserDisc)"}),
                "creases": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01,
                                      "tooltip": "Tape creases: diagonal bright kink lines that persist for a while. No effect on LaserDisc (optical media)"}),
                "ghosting": ("FLOAT", {"default": 0.30, "min": 0.0, "max": 1.0, "step": 0.01,
                                       "tooltip": "Frame ghosting / crosstalk: previous frame bleeds through with an offset"}),
                "head_switch": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 1.0, "step": 0.01,
                                          "tooltip": "Head-switching noise bar at the bottom of the frame (VHS/BetaMax only)"}),
                "vertical_roll": ("FLOAT", {"default": 0.15, "min": 0.0, "max": 1.0, "step": 0.01,
                                            "tooltip": "Vertical hold failures: image rolls with a blanking bar. Low values give gentle vertical jitter"}),
                "tape_noise": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01,
                                         "tooltip": "Analog tape grain: luma + chroma noise"}),
                "flicker": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.01,
                                      "tooltip": "Luminance instability: slow brightness wobble"}),
                "luma_softness": ("FLOAT", {"default": 0.50, "min": 0.0, "max": 1.0, "step": 0.01,
                                            "tooltip": "Video bandwidth: how soft the luma is. VHS is softest, LaserDisc sharpest (scaled by format)"}),
                "color_bleed": ("FLOAT", {"default": 0.50, "min": 0.0, "max": 1.0, "step": 0.01,
                                          "tooltip": "Composite chroma smear: colors bleed sideways and oversaturate"}),
                "scanlines": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.01,
                                        "tooltip": "Interlaced line structure: every other line slightly darker"}),
                "wear_start": ("INT", {"default": 0, "min": 0, "max": 1000000,
                                       "tooltip": "Worn section start frame. Damage spikes inside [wear_start, wear_end) with 4-frame ramps"}),
                "wear_end": ("INT", {"default": 0, "min": 0, "max": 1000000,
                                     "tooltip": "Worn section end frame. Leave <= wear_start to disable"}),
                "wear_boost": ("FLOAT", {"default": 0.60, "min": 0.0, "max": 1.0, "step": 0.01,
                                         "tooltip": "How much worse the tape gets inside the worn section"}),
                "osd_enabled": ("BOOLEAN", {"default": True, "tooltip": "Draw the VCR on-screen display"}),
                "osd_mode": (["play", "rec", "none"],
                             {"tooltip": "Status overlay: PLAY triangle or blinking REC dot (top-left)"}),
                "osd_color": (["white", "teal", "amber"],
                              {"tooltip": "Classic VCR white, camcorder teal or date-stamp amber"}),
                "osd_counter": ("BOOLEAN", {"default": True, "tooltip": "Tape counter (h:mm:ss) top-right"}),
                "osd_counter_start": ("INT", {"default": 0, "min": 0, "max": 1000000,
                                              "tooltip": "Counter value at frame 0, in seconds"}),
                "osd_custom_text": ("STRING", {"default": "DEC 24 1996",
                                               "tooltip": "Custom stamp bottom-right (date, SP/EP, ...). A-Z 0-9 : . - / ( ) ' supported"}),
                "osd_scale": ("INT", {"default": 2, "min": 1, "max": 8,
                                      "tooltip": "OSD pixel size. Increase for high-res images"}),
                "osd_fps": ("INT", {"default": 24, "min": 1, "max": 120,
                                    "tooltip": "Frames per second used for the counter and REC blink"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF,
                                 "tooltip": "Random seed. Same seed = same damage, everywhere"}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    OUTPUT_TOOLTIPS = ("The tape-damaged image / video batch",)
    FUNCTION = "apply"

    def apply(
        self,
        image,
        format,
        preset,
        tracking,
        dropout,
        creases,
        ghosting,
        head_switch,
        vertical_roll,
        tape_noise,
        flicker,
        luma_softness,
        color_bleed,
        scanlines,
        wear_start,
        wear_end,
        wear_boost,
        osd_enabled,
        osd_mode,
        osd_color,
        osd_counter,
        osd_counter_start,
        osd_custom_text,
        osd_scale,
        osd_fps,
        seed,
    ):
        if image.ndim == 3:
            image = image.unsqueeze(0)
        img = image.detach().clone().float()
        b, h, w, _ = img.shape
        device = img.device

        # Degenerate tiny inputs: nothing meaningful to degrade.
        if h < 32 or w < 32:
            return (img,)

        prof = FORMAT_PROFILES[format]
        pm = PRESET_MULT[preset]
        seed = int(seed)
        sf = max(h, w) / 640.0

        wear = _wear_mask(b, wear_start, wear_end)
        dmg = pm * (1.0 + 1.6 * wear_boost * wear)

        s_track = np.clip(tracking * prof["tracking"] * dmg, 0.0, 1.6)
        s_drop = np.clip(dropout * prof["dropout_amount"] * dmg, 0.0, 1.6)
        s_crease = np.clip(creases * prof["creases"] * dmg, 0.0, 1.6)
        s_ghost = np.clip(ghosting * prof["ghost"] * (0.35 + 0.65 * dmg), 0.0, 1.2)
        s_head = np.clip(head_switch * prof["head_switch"] * (0.35 + 0.65 * dmg), 0.0, 1.0)
        s_roll = np.clip(vertical_roll * prof["vertical_roll"] * dmg, 0.0, 1.5)
        s_noise = np.clip(
            tape_noise * prof["noise"] * (0.30 + 0.70 * dmg) * (1.0 + 0.8 * wear), 0.0, 1.5
        )
        s_flick = np.clip(flicker * prof["flicker"] * (0.40 + 0.60 * dmg), 0.0, 1.0)

        soft = luma_softness * prof["luma_blur"]
        bleed = color_bleed * prof["chroma_bleed"]
        luma_sigma = sf * (0.25 + 2.4 * soft)
        chroma_sigma = sf * (0.5 + 3.2 * bleed)
        chroma_shift = int(round(sf * (0.5 + 2.5 * bleed)))

        schedule = _build_schedule(b, seed, s_track, s_roll, s_crease)

        ctx = {
            "prof": prof,
            "sf": sf,
            "luma_sigma": luma_sigma,
            "chroma_sigma": chroma_sigma,
            "chroma_shift": chroma_shift,
            "chroma_gain": prof["chroma_gain"],
            "dmg": dmg,
            "s_track": s_track,
            "s_drop": s_drop,
            "s_crease": s_crease,
            "s_ghost": s_ghost,
            "s_head": s_head,
            "s_roll": s_roll,
            "s_noise": s_noise,
            "s_flick": s_flick,
            "scan": float(scanlines),
            "schedule": schedule,
            "prev": torch.zeros(3, h, w, device=device),
            "crease_cache": {},
            "osd": bool(osd_enabled) and (osd_mode != "none" or osd_counter or bool(osd_custom_text)),
            "osd_mode": osd_mode,
            "osd_rgb": OSD_COLORS.get(osd_color, OSD_COLORS["white"]),
            "osd_counter": bool(osd_counter),
            "osd_counter_start": int(osd_counter_start),
            "osd_custom": str(osd_custom_text).strip(),
            "osd_scale": int(osd_scale),
            "osd_fps": int(osd_fps),
            "osd_cache": {},
            "frame_seed": lambda i: (seed * 1000003 + i * 7919) % (2**62),
            "drop_seed": lambda i: (seed * 7919 + (i // 2) * 2654435761 + 97) % (2**62),
        }

        out = torch.empty_like(img)
        for i in range(b):
            frame = img[i].permute(2, 0, 1).contiguous()
            frame = _process_frame(frame, i, ctx)
            out[i] = frame.permute(1, 2, 0)
        return (out,)

