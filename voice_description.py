"""Local, read-only voice analysis for library editors."""
import io
import math

import av
import numpy as np

from .voice_analysis_vendor.analysis import analyze_waveform
from .voice_analysis_vendor.timbre_map import describe_timbre


def describe_audio(audio):
    rate = int(audio["sample_rate"])
    if rate <= 0:
        raise ValueError("Audio has an invalid sample rate.")
    waveform = audio["waveform"][..., :math.floor(15 * rate)]
    if hasattr(waveform, "detach"):
        waveform = waveform.detach().float().cpu().numpy()
    waveform = np.asarray(waveform, dtype=np.float32)
    if waveform.ndim == 3:
        waveform = waveform[0]
    if waveform.ndim == 2:
        waveform = waveform.mean(axis=0)
    if waveform.ndim != 1 or waveform.size < math.ceil(.3 * rate):
        raise ValueError("Use at least 0.3 seconds of audible voice.")
    if not np.isfinite(waveform).all():
        raise ValueError("Audio contains invalid samples. Choose another recording.")
    if np.max(np.abs(waveform)) < 1e-6:
        raise ValueError("The selected audio is silent. Choose a section with audible voice.")
    metrics = analyze_waveform(waveform.copy(), rate)
    return {"description": describe_timbre(metrics), "seconds": len(waveform) / rate}


def describe_file(source):
    """Decode at most fifteen seconds, including unsaved multipart uploads."""
    source = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else str(source)
    parts = []
    count = 0
    try:
        with av.open(source) as container:
            if not container.streams.audio:
                raise ValueError("The selected file has no audio track.")
            stream = container.streams.audio[0]
            rate = stream.codec_context.sample_rate
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=rate)
            for frame in container.decode(stream):
                for converted in resampler.resample(frame):
                    part = converted.to_ndarray()[0][:max(0, 15 * rate - count)]
                    parts.append(part)
                    count += len(part)
                if count >= 15 * rate:
                    break
    except av.error.FFmpegError as error:
        raise ValueError("Could not read this audio. Upload a valid voice recording.") from error
    return describe_audio({"waveform": np.concatenate(parts) if parts else np.array([]), "sample_rate": rate})
