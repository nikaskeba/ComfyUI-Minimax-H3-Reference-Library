"""Waveform processing shared by immediate and deferred reference loading."""
import math


def crop_voice_reference(audio, max_seconds):
    if max_seconds is None:
        return audio
    waveform = audio["waveform"]
    samples = math.floor(float(max_seconds) * int(audio["sample_rate"]))
    if waveform.shape[-1] <= samples:
        return audio
    return {**audio, "waveform": waveform[..., :samples].clone()}
