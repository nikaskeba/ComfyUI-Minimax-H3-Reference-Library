"""Connected-audio adapter for the installed ComfyUI-YuE2-Trainer."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

import folder_paths
import nodes
import soundfile as sf
import torch
from comfy_api.latest import io


def stage_tracks(tracks, root):
    """Content-addressed FLOAT WAVs preserve input samples and stable cache paths."""
    prepared = []
    digest = hashlib.sha256()
    for name in sorted(tracks, key=lambda name: int(name.rsplit("_", 1)[-1])):
        audio = tracks[name]
        if audio is None:
            continue
        wave = audio["waveform"].detach().to(device="cpu", dtype=torch.float32).contiguous()
        rate = int(audio["sample_rate"])
        if wave.ndim != 3 or min(wave.shape) < 1 or rate <= 0:
            raise ValueError(f"{name}: expected nonempty AUDIO [batch, channels, samples] and a positive sample rate.")
        if not torch.isfinite(wave).all():
            raise ValueError(f"{name}: audio contains non-finite samples.")
        for item in wave:
            data = item.numpy().T.copy()
            digest.update(json.dumps([rate, list(data.shape)]).encode())
            digest.update(data.tobytes())
            prepared.append((data, rate))
    if not prepared:
        raise ValueError("Connect at least one audio track.")
    folder = Path(root) / digest.hexdigest() / "sources"
    folder.mkdir(parents=True, exist_ok=True)
    for index, (data, rate) in enumerate(prepared):
        target = folder / f"track_{index + 1:04}.wav"
        if target.is_file():
            continue
        handle, temporary = tempfile.mkstemp(suffix=".wav", dir=folder)
        os.close(handle)
        try:
            sf.write(temporary, data, rate, subtype="FLOAT")
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return folder


class SkebaYuE2TrainingDataset(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaYuE2TrainingDataset",
            display_name="SKEBA YuE2 Training Dataset (audio inputs)",
            category="Skeba Music",
            description="Connect training tracks directly. Uses the installed YuE2 Trainer's native checkpoint VAE, clipping and latent cache. Working WAVs are saved automatically.",
            inputs=[
                io.Combo.Input("checkpoint", options=folder_paths.get_filename_list("checkpoints") or ["No checkpoints found"]),
                io.Autogrow.Input("tracks", template=io.Autogrow.TemplatePrefix(io.Audio.Input("audio"), prefix="audio_", min=1, max=100)),
                io.Float.Input("clip_seconds", default=10.0, min=1.0, max=60.0, step=0.5),
                io.Combo.Input("caption_mode", options=["default", "none"], default="default"),
                io.String.Input("default_caption", default="", multiline=True, tooltip="Caption applied to every track in default mode."),
                io.String.Input("cache_folder", default="", tooltip="Optional cache root. Empty uses ComfyUI temp/yue2_connected_tracks. Includes working WAVs and encoded latents."),
                io.Boolean.Input("force_reencode", default=False),
            ],
            outputs=[io.Custom("YUE2_TRAIN_DATASET").Output(display_name="dataset"), io.String.Output(display_name="summary")],
        )

    @classmethod
    def execute(cls, checkpoint, tracks, clip_seconds=10.0, caption_mode="default",
                default_caption="", cache_folder="", force_reencode=False):
        trainer = nodes.NODE_CLASS_MAPPINGS.get("YuE2TrainingDataset")
        if trainer is None:
            raise ValueError("Install/enable ComfyUI-YuE2-Trainer and restart ComfyUI before using this dataset node.")
        checkpoint_path = Path(folder_paths.get_full_path_or_raise("checkpoints", checkpoint))
        stat = checkpoint_path.stat()
        checkpoint_key = hashlib.sha256(f"{checkpoint_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode()).hexdigest()[:24]
        root = Path(cache_folder.strip().strip('"')) if cache_folder.strip() else Path(folder_paths.get_temp_directory()) / "yue2_connected_tracks"
        folder = stage_tracks(tracks, root)
        # Isolate re-encoding from other datasets, checkpoints and clip settings.
        cache = folder.parent / "latents" / checkpoint_key / str(float(clip_seconds))
        dataset, summary = trainer().build(checkpoint, str(folder), clip_seconds, caption_mode,
                                          default_caption, str(cache), force_reencode)
        return io.NodeOutput(dataset, summary)
