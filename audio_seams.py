"""Short, duration-preserving fades at export boundaries only."""
import math
import numpy as np


def seam_samples(total, rate, milliseconds):
    milliseconds = float(milliseconds)
    if not math.isfinite(milliseconds) or not 0 <= milliseconds <= 50:
        raise ValueError("Audio seam smoothing must be between 0 and 50 ms.")
    return min(total // 2, round(rate * milliseconds / 2000))


def seam_gain(start, count, total, fade, fade_in, fade_out):
    positions = np.arange(start, start + count)
    gain = np.ones(count)
    if fade:
        if fade_in:
            gain *= 0.5 - 0.5 * np.cos(np.pi * np.clip(positions / max(1, fade - 1), 0, 1))
        if fade_out:
            gain *= 0.5 - 0.5 * np.cos(np.pi * np.clip((total - 1 - positions) / max(1, fade - 1), 0, 1))
    return gain
