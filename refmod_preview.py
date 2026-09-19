"""Queued VAE previews of stored RefMod frames and audio."""
import json
import uuid
import wave
from pathlib import Path

import folder_paths
from PIL import Image
import comfy.model_management as mm
import comfy.utils
from .refmod_studio import members_from_file


class SkebaRefModPreview:
    CATEGORY = "Skeba AI Nodes - Reference"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("preview_details",)
    FUNCTION = "preview"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"spec": ("STRING", {"default": "{}"})},
                "optional": {"vae": ("VAE",), "audio_vae": ("VAE",)}}

    @classmethod
    def IS_CHANGED(cls, **kwargs): return float("nan")

    def preview(self, spec, vae=None, audio_vae=None):
        settings=json.loads(spec)
        _,_,mods=members_from_file(settings["existing"])
        if settings.get("companion"):
            _,_,extra=members_from_file(settings["companion"]); mods.extend(extra)
        visual=next((m for m in mods if m.kind != "audio"),None)
        audio=next((m for m in mods if m.kind == "audio"),None)
        if visual is not None and vae is None: raise ValueError("Select an H3 video VAE to preview stored frames.")
        if audio is not None and audio_vae is None: raise ValueError("Select an H3 audio VAE to preview the stored voice.")
        root=Path(folder_paths.get_temp_directory()) / "skeba_refmod_previews"
        root.mkdir(parents=True,exist_ok=True)
        prefix=uuid.uuid4().hex
        result={"frames":[],"audio":None}
        def entry(name): return {"filename":name,"subfolder":"skeba_refmod_previews","type":"temp"}
        progress=comfy.utils.ProgressBar((visual.latent_t if visual else 0) + (1 if audio else 0))
        if visual:
            for i in range(visual.latent_t):
                mm.throw_exception_if_processing_interrupted()
                pixels=vae.decode(visual.latent[:,:,i:i+1].clone())
                if pixels.ndim==5: pixels=pixels.reshape(-1,*pixels.shape[-3:])
                name=f"{prefix}_{i}.png"
                Image.fromarray((pixels[0].detach().float().cpu().clamp(0,1).numpy()*255).astype("uint8")).save(root/name)
                result["frames"].append(entry(name)); progress.update(1)
        if audio:
            mm.throw_exception_if_processing_interrupted()
            decoded=audio_vae.decode(audio.latent).detach().float().cpu()
            rate=int(getattr(audio_vae,"audio_sample_rate_output",getattr(audio_vae,"audio_sample_rate",32000)))
            name=prefix+".wav"
            with wave.open(str(root/name),"wb") as handle:
                handle.setnchannels(decoded.shape[-1]);handle.setsampwidth(2);handle.setframerate(rate)
                handle.writeframes((decoded[0].clamp(-1,1).numpy()*32767).round().astype("<i2").tobytes())
            result["audio"]=entry(name);progress.update(1)
        return {"ui":{"refmod_preview":[result]},"result":(json.dumps(result),)}
