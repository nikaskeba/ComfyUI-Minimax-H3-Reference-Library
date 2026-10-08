"""Voice timbre analysis core for ComfyUI nodes.

Primary backend: librosa (pyin F0 tracking, spectral features, LPC formants).
Fallback: pure-numpy implementation if librosa is unavailable.

Entry point: analyze_waveform(x, sr) so nodes can consume LoadAudio's
waveform tensor directly (no ffmpeg decode needed).
"""
import numpy as np

SR = 24000

try:
    import librosa
    HAS_LIBROSA = True
except Exception:
    HAS_LIBROSA = False


def _pyin_f0(x, sr):
    """Accurate F0 track via librosa.yin (fast YIN tracker).

    Unlike pyin, plain yin emits an F0 for every frame (no voiced
    probability), so octave/half-octave gross errors and unvoiced-frame
    garbage must be removed afterwards:
      1. reject frames whose F0 deviates >~45% from the running median;
      2. reject frames with implausible frame-to-frame jumps (>25%).
    Returns 1-D array of cleaned F0 values in Hz, or None.
    """
    x16 = librosa.resample(x, orig_sr=sr, target_sr=16000)
    f0 = librosa.yin(x16, fmin=60, fmax=500, sr=16000,
                     frame_length=2048, hop_length=int(0.010 * 16000))
    f0 = np.asarray(f0, dtype=np.float64)
    f0 = f0[np.isfinite(f0)]
    if len(f0) < 5:
        return f0 if len(f0) else None
    # iteratively converge on a robust median, dropping octave outliers
    for _ in range(2):
        med = np.median(f0)
        keep = (f0 >= 0.55 * med) & (f0 <= 1.80 * med)
        if keep.all():
            break
        f0 = f0[keep]
        if len(f0) < 5:
            break
    # continuity filter: jump vs the previous *kept* frame (>33% in 10 ms
    # is an octave-error artifact, not a realistic pitch glide)
    if len(f0) > 5:
        cleaned = [f0[0]]
        for v in f0[1:]:
            ratio = v / cleaned[-1]
            if 0.75 <= ratio <= 1.33:
                cleaned.append(v)
        if len(cleaned) >= 5:
            f0 = np.asarray(cleaned)
    return f0 if len(f0) else None


def _formants_lpc(frames, sr, max_frames=120):
    """Estimate F1/F2/F3 (median Hz) via LPC on voiced frames.

    Vocal-tract resonances are among the strongest timbre discriminators
    (a longer vocal tract produces lower formant frequencies).
    """
    order = max(8, sr // 1000 + 4)
    out = {"f1": [], "f2": [], "f3": []}
    if len(frames) > max_frames:  # uniform subsample for speed
        idx = np.linspace(0, len(frames) - 1, max_frames).astype(int)
        frames = frames[idx]
    win = np.hanning(frames.shape[1])
    for fr in frames:
        fr = (fr - fr.mean()) * win
        if (fr ** 2).sum() < 1e-8:
            continue
        try:
            a = librosa.lpc(fr, order=order)
        except Exception:
            continue
        roots = np.roots(a)
        roots = roots[np.imag(roots) >= 0]
        angz = np.arctan2(np.imag(roots), np.real(roots))
        # bandwidth filter: reject unrealistically sharp/wide poles
        bw = -0.5 * (sr / (2 * np.pi)) * np.log(np.abs(roots) + 1e-12)
        frq = angz * (sr / (2 * np.pi))
        keep = (frq > 90) & (bw < 500) & (frq < sr / 2 - 100)
        frq = np.sort(frq[keep])
        if len(frq) >= 1:
            out["f1"].append(frq[0])
        if len(frq) >= 2:
            out["f2"].append(frq[1])
        if len(frq) >= 3:
            out["f3"].append(frq[2])
    return {k: float(np.median(v)) if v else float("nan") for k, v in out.items()}


def _phrasing_metrics(mask, hop_seconds):
    """Measure internal pauses; exclude leading/trailing recording silence.

    Join energy gaps under 120 ms so individual consonants are less likely to
    be mistaken for phrase boundaries. This is an energy heuristic, not ASR.
    """
    active = np.flatnonzero(mask)
    if len(active) < 2:
        return {}
    gaps = np.flatnonzero(np.diff(active) * hop_seconds >= .12 + hop_seconds)
    starts = np.r_[active[0], active[gaps + 1]]
    ends = np.r_[active[gaps], active[-1]]
    phrases = (ends - starts + 1) * hop_seconds
    pauses = (starts[1:] - ends[:-1] - 1) * hop_seconds
    span = (active[-1] - active[0] + 1) * hop_seconds
    return {
        "phrase_count": len(phrases),
        "phrase_seconds_median": float(np.median(phrases)),
        "phrase_duration_cv": float(phrases.std() / phrases.mean()),
        "pause_count": len(pauses),
        "pause_seconds_median": float(np.median(pauses)) if len(pauses) else 0.0,
        "pause_ratio": float(pauses.sum() / span),
    }


def analyze_waveform(x, sr, path=""):
    """Core analysis on a mono float32 waveform (peak-normalized inside)."""
    x = x / (np.max(np.abs(x)) + 1e-9)
    dur = len(x) / sr

    # --- energy VAD: 25ms frame / 10ms hop ---
    fl, hop = int(0.025 * sr), int(0.010 * sr)
    n = (len(x) - fl) // hop
    frames = np.lib.stride_tricks.sliding_window_view(x, fl)[::hop][:n]
    rms = np.sqrt((frames ** 2).mean(axis=1))
    mask = rms > max(rms.max() * 0.06, rms.mean() * 0.35)
    vf = frames[mask]

    db = 20 * np.log10(rms[rms > 1e-6] + 1e-9)
    active_db = 20 * np.log10(rms[mask] + 1e-9)
    phrasing = _phrasing_metrics(mask, hop / sr)

    # --- F0: librosa pyin (accurate, octave-error-resistant) or numpy fallback ---
    if HAS_LIBROSA:
        f0s = _pyin_f0(x, sr)
        if f0s is None:
            f0s = np.array([])
    else:
        f0s = []
        lo, hi = int(sr / 400), int(sr / 60)
        for fr in vf:
            fr = fr - fr.mean()
            if (fr ** 2).sum() < 1e-8:
                continue
            ac = np.correlate(fr, fr, mode="full")[fl - 1:]
            if ac[0] <= 0:
                continue
            ac /= ac[0]
            seg = ac[lo:hi]
            if len(seg) < 2:
                continue
            pk = np.argmax(seg) + lo
            if ac[pk] > 0.45:
                f0s.append(sr / pk)
        f0s = np.array(f0s)

    # --- spectral features on voiced frames ---
    freqs = np.fft.rfftfreq(4096, 1 / sr)
    win = np.hanning(fl)
    LTS = np.zeros(len(freqs))
    cent, roll85, flat = [], [], []
    for fr in vf:
        fr = fr - fr.mean()
        S = np.abs(np.fft.rfft(fr * win, n=4096))
        P = S ** 2 + 1e-12
        cent.append((freqs * P).sum() / P.sum())
        cum = np.cumsum(P) / P.sum()
        roll85.append(freqs[np.searchsorted(cum, 0.85)])
        flat.append(np.exp(np.log(P + 1e-12).mean()) / (P.mean() + 1e-12))
        LTS += P
    LTS /= max(len(vf), 1)
    cent = np.array(cent); roll85 = np.array(roll85); flat = np.array(flat)
    tot = LTS.sum()
    bands = {}
    for name, lo_b, hi_b in [("sub", 20, 80), ("low", 80, 250), ("lowmid", 250, 500),
                             ("mid", 500, 1500), ("highmid", 1500, 3000),
                             ("sib", 3000, 6000), ("airy", 6000, 12000)]:
        m = (freqs >= lo_b) & (freqs < hi_b)
        bands[name] = 100 * LTS[m].sum() / tot

    # --- spectral shape descriptors for timbre discrimination ---
    # low-frequency dominance: % of total energy below 250 Hz
    low_energy = bands["sub"] + bands["low"]
    # spectral spread (std dev around centroid) on the long-term spectrum
    lt_cent = (freqs * LTS).sum() / tot
    lt_spread = np.sqrt(((freqs - lt_cent) ** 2 * LTS).sum() / tot)
    # peak-to-average ratio of the long-term spectrum (harmonic richness)
    lt_par = float(LTS.max() / (LTS.mean() + 1e-12))
    # spectral tilt: linear regression slope of log-spectrum vs log-freq (dB/decade)
    valid = (freqs > 50) & (LTS > 1e-10)
    if valid.sum() > 10:
        logf = np.log10(freqs[valid])
        logp = 10 * np.log10(LTS[valid])
        tilt = float(np.polyfit(logf, logp, 1)[0])
    else:
        tilt = float("nan")

    # --- rhythm ---
    d = mask.astype(int)
    transitions = int(np.abs(np.diff(d)).sum())
    runs, cur = [], 0
    for v in d:
        if v:
            cur += 1
        else:
            if cur:
                runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    longest = max(runs) * hop / sr if runs else 0.0

    jitter = float(np.mean(np.abs(np.diff(f0s)) / f0s[:-1])) if len(f0s) > 5 else float("nan")

    # --- formants (vocal tract resonances) via librosa LPC ---
    if HAS_LIBROSA:
        formants = _formants_lpc(vf, sr)
    else:
        formants = {"f1": float("nan"), "f2": float("nan"), "f3": float("nan")}

    return {
        **phrasing,
        "active_level_span_db": float(np.percentile(active_db, 90) - np.percentile(active_db, 10)) if len(active_db) else float("nan"),
        "path": path, "duration": dur, "active_ratio": float(mask.mean()),
        "backend": "librosa" if HAS_LIBROSA else "numpy",
        "level_dbfs": float(db.mean()) if len(db) else float("nan"),
        "level_range": (float(db.min()), float(db.max())) if len(db) else (float("nan"), float("nan")),
        "f0_mean": float(f0s.mean()) if len(f0s) else float("nan"),
        "f0_median": float(np.median(f0s)) if len(f0s) else float("nan"),
        "f0_p10": float(np.percentile(f0s, 10)) if len(f0s) else float("nan"),
        "f0_p90": float(np.percentile(f0s, 90)) if len(f0s) else float("nan"),
        "f0_std": float(f0s.std()) if len(f0s) else float("nan"),
        "f0_span_st": float(12 * np.log2(np.percentile(f0s, 90) / np.percentile(f0s, 10))) if len(f0s) else float("nan"),
        "centroid_median": float(np.median(cent)) if len(cent) else float("nan"),
        "rolloff85_median": float(np.median(roll85)) if len(roll85) else float("nan"),
        "flatness": float(flat.mean()) if len(flat) else float("nan"),
        "bands": bands,
        "low_energy": float(low_energy),
        "spectral_spread": float(lt_spread),
        "spectral_tilt": float(tilt) if tilt == tilt else None,
        "harmonic_par": float(lt_par),
        "formant_f1": formants["f1"],
        "formant_f2": formants["f2"],
        "formant_f3": formants["f3"],
        "jitter": jitter, "transitions": transitions, "longest_voiced": float(longest),
        "tps": transitions / dur,
    }
