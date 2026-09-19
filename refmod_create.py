"""Queueable, local RefMod creation from saved library media."""
import json
import re
import uuid

from PIL import Image
from safetensors.torch import save_file
from comfy_extras import nodes_minimax_h3 as h3

from .library import get_record, media_path
from .built_in_references import library_built_in_records
from .h3_tag_references import load_image, load_audio, load_video
from .refmod_library import roots
from .refmod_runtime import H3RefMod


class SkebaCreateH3RefMod:
    CATEGORY = "Skeba AI Nodes - Reference"
    RETURN_TYPES = ("STRING", "H3_REF_MODS")
    RETURN_NAMES = ("file", "mods")
    FUNCTION = "create"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "vae": ("VAE",),
            "record_id": ("STRING", {"default": ""}),
            "kind": (["image", "video", "audio"],),
            "name": ("STRING", {"default": "reference"}),
            "max_side": ("INT", {"default": 768, "min": 64, "max": 2048, "step": 32}),
            "max_seconds": ("FLOAT", {"default": 15.0, "min": 0.1, "max": 60.0}),
        }}

    def create(self, vae, record_id, kind, name, max_side=768, max_seconds=15.0):
        if record_id.startswith("built-in:"):
            record = library_built_in_records()[record_id[len("built-in:"):]]
        else:
            record = get_record(record_id)
        path = media_path(record, kind)
        preview = None
        if kind == "audio":
            audio = load_audio(path)
            samples = int(float(max_seconds) * audio["sample_rate"])
            audio = {**audio, "waveform": audio["waveform"][..., :samples]}
            latent, _ = h3._encode_ref_audio(vae, audio)
        else:
            pixels = load_image(path) if kind == "image" else load_video(path, 24, max_side)[0]
            pixels = pixels[:1] if kind == "image" else pixels[:max(1, int(max_seconds * 24))]
            height, width = pixels.shape[1:3]
            scale = min(1.0, float(max_side) / max(height, width))
            width, height = (max(32, int(round(value * scale / 32)) * 32) for value in (width, height))
            pixels = h3._resize(pixels, width, height, "disabled")
            preview = Image.fromarray((pixels[0].detach().cpu().clamp(0, 1).numpy() * 255).astype("uint8"))
            latent = vae.encode(pixels)
        latent = latent.detach().cpu().contiguous()
        mod = H3RefMod(name=name, kind=kind, latent=latent, mode="encode")
        meta = {"name": name, "kind": kind, "mode": "encode", "latent_h": mod.latent_h,
                "latent_w": mod.latent_w, "latent_t": mod.latent_t, "fps": 24,
                "sample_rate": int(getattr(vae, "audio_sample_rate", 32000)),
                "source": record["tag"], "description": record.get(kind + "_description", "")}
        safe = re.sub(r"[^\w-]+", "_", name).strip("_")[:80] or "reference"
        relative = "library/" + safe + "_" + uuid.uuid4().hex[:12] + ".safetensors"
        target = roots()[0] / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        try:
            save_file({"latent": latent}, str(temporary), metadata={"refmod_meta": json.dumps(meta)})
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        if preview is not None:
            preview.save(target.with_suffix(".png"))
        return {"ui": {"text": [relative]}, "result": (relative, [(mod, 1.0)])}
