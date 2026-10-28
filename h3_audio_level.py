"""Gentle post-decode level control for H3 AUDIO outputs."""

import torch
import torch.nn.functional as F


def _moving_average(values, width):
    width = max(1, int(width) | 1)
    return F.avg_pool1d(F.pad(values, (width // 2, width // 2), mode="replicate"),
                        kernel_size=width, stride=1)


def normalize_audio(audio, target_db=-22.0, strength=0.7, max_boost_db=6.0,
                    max_cut_db=12.0, gate_db=-38.0, low_cut_hz=75.0,
                    presence_db=1.0, peak_ceiling_db=-1.0):
    """Return a new AUDIO dict; use one gain envelope for all channels."""
    samples = audio.get("waveform")
    rate = int(audio.get("sample_rate", 0))
    if not isinstance(samples, torch.Tensor) or samples.ndim != 3 or samples.shape[-1] == 0:
        raise ValueError("Expected AUDIO waveform [batch, channels, samples] with samples present.")
    if rate <= 0 or samples.shape[1] < 1:
        raise ValueError("AUDIO needs a positive sample rate and at least one channel.")
    if not torch.isfinite(samples).all():
        raise ValueError("AUDIO contains NaN or infinite samples.")

    work = samples.to(torch.float32)
    length = work.shape[-1]
    if low_cut_hz > 0 or presence_db != 0:
        frequencies = torch.fft.rfftfreq(length, 1.0 / rate, device=work.device)
        response = torch.ones_like(frequencies)
        if low_cut_hz > 0:
            response *= frequencies / torch.sqrt(frequencies.square() + low_cut_hz ** 2)
        if presence_db != 0:
            octaves = torch.log2(frequencies.clamp(min=1.0) / 3000.0)
            bell = torch.exp(-0.5 * (octaves / 0.7).square())
            response *= torch.pow(10.0, presence_db * bell / 20.0)
        work = torch.fft.irfft(torch.fft.rfft(work, dim=-1) * response, n=length, dim=-1)

    # Ten-millisecond measurements, a 250 ms RMS window, and a 200 ms gain
    # smoothing window avoid per-sample pumping without processing every sample
    # through a long convolution.
    hop = max(1, round(rate / 100))
    pad = (-length) % hop
    power = work.square().mean(dim=1, keepdim=True)
    if pad:
        power = F.pad(power, (0, pad))
    power = power.reshape(work.shape[0], 1, -1, hop).mean(dim=-1)
    rms = _moving_average(power, 25).clamp_min(1e-12).sqrt()
    level_db = 20.0 * torch.log10(rms)
    gain_db = ((target_db - level_db) * strength).clamp(-max_cut_db, max_boost_db)
    gain_db = torch.where(level_db >= gate_db, gain_db, torch.zeros_like(gain_db))
    gain_db = _moving_average(gain_db, 21)
    gain = torch.pow(10.0, gain_db / 20.0)
    gain = F.interpolate(gain, size=length, mode="linear", align_corners=False)
    result = work * gain

    ceiling = 10.0 ** (peak_ceiling_db / 20.0)
    peak = result.abs().amax(dim=(1, 2), keepdim=True)
    result = result * (ceiling / peak.clamp_min(1e-12)).clamp(max=1.0)
    return {**audio, "waveform": result.to(samples.dtype)}


class SkebaH3AudioLevel:
    CATEGORY = "Skeba AI Nodes - Audio"
    FUNCTION = "process"
    RETURN_TYPES = ("AUDIO", "STRING")
    RETURN_NAMES = ("audio", "status")
    DESCRIPTION = (
        "Even out decoded dialogue with gentle windowed level control, a low cut, "
        "and optional speech-presence EQ. Processes the entire mix; it cannot "
        "identify or isolate individual speakers."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "audio": ("AUDIO",),
            "enabled": ("BOOLEAN", {"default": True}),
            "target_voice_dbfs": ("FLOAT", {"default": -22.0, "min": -36.0, "max": -10.0, "step": 0.5,
                                         "tooltip": "Target short-window RMS level for audible material; this is not LUFS."}),
            "level_strength": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.05,
                                        "tooltip": "How strongly quiet and loud passages move toward the target."}),
            "max_boost_db": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 18.0, "step": 0.5}),
            "max_cut_db": ("FLOAT", {"default": 12.0, "min": 0.0, "max": 24.0, "step": 0.5}),
            "quiet_gate_dbfs": ("FLOAT", {"default": -38.0, "min": -70.0, "max": -20.0, "step": 1.0,
                                        "tooltip": "Material below this level is not boosted, reducing room-noise pumping."}),
            "low_cut_hz": ("FLOAT", {"default": 75.0, "min": 0.0, "max": 200.0, "step": 5.0}),
            "presence_db": ("FLOAT", {"default": 1.0, "min": -6.0, "max": 6.0, "step": 0.5,
                                      "tooltip": "Broad 3 kHz voice-presence EQ. Set zero to disable."}),
            "peak_ceiling_dbfs": ("FLOAT", {"default": -1.0, "min": -6.0, "max": -0.1, "step": 0.1}),
        }}

    def process(self, audio, enabled=True, target_voice_dbfs=-22.0, level_strength=0.7,
                max_boost_db=6.0, max_cut_db=12.0, quiet_gate_dbfs=-38.0,
                low_cut_hz=75.0, presence_db=1.0, peak_ceiling_dbfs=-1.0):
        if not enabled:
            return audio, "Audio level processing bypassed."
        output = normalize_audio(audio, target_voice_dbfs, level_strength, max_boost_db,
                                 max_cut_db, quiet_gate_dbfs, low_cut_hz, presence_db,
                                 peak_ceiling_dbfs)
        return output, (f"Level control target {target_voice_dbfs:g} dBFS RMS; "
                        f"max boost {max_boost_db:g} dB, cut {max_cut_db:g} dB; "
                        f"low cut {low_cut_hz:g} Hz; presence {presence_db:+g} dB. "
                        "Entire mix processed; speaker separation is not performed.")
