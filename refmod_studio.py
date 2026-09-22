"""RefMod studio source storage and queued create/edit jobs."""
import json
import math
import os
import re
import shutil
import uuid
from pathlib import Path

import folder_paths
import torch
import comfy.model_management as mm
import comfy.utils
from PIL import Image
from safetensors.torch import save_file
from comfy_extras import nodes_minimax_h3 as h3

from .h3_tag_references import load_image, load_video, load_audio
from .refmod_library import roots, resolve, read_meta
from .refmod_runtime import H3RefMod
from .refmod_training import aspect_grid, encode_look, join_audio, pool_latent, optimize_latent, _cover, ensure_min_size, snap_to_h3_grid

SOURCE_EXTENSIONS = {".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".bmp": "image",
                     ".mp4": "video", ".mkv": "video", ".mov": "video", ".webm": "video", ".avi": "video",
                     ".wav": "audio", ".mp3": "audio", ".flac": "audio", ".ogg": "audio", ".m4a": "audio", ".opus": "audio"}


def source_root():
    return Path(folder_paths.get_input_directory()) / "skeba_refmod_sources"


def source_path(name):
    root = source_root().resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or Path(name).name != name or path.suffix.lower() not in SOURCE_EXTENSIONS:
        raise ValueError("Invalid RefMod source file.")
    if not path.is_file():
        raise FileNotFoundError("Source upload is missing: " + name)
    return path


def output_path(name):
    relative = Path(name)
    if relative.suffix.lower() != ".safetensors": relative = relative.with_suffix(".safetensors")
    root = roots()[0].resolve()
    target = (root / relative).resolve()
    if relative.is_absolute() or ".." in relative.parts or not target.is_relative_to(root):
        raise ValueError("Save inside a registered RefMod folder using a relative file name.")
    if not relative.stem or any(c in str(relative) for c in '<>:"|?*'):
        raise ValueError("Invalid RefMod file name.")
    return target, relative.as_posix()


def members_from_file(selection):
    path, _ = resolve(selection)
    meta, _ = read_meta(str(path.with_suffix("")))
    indices = range(len(meta["members"])) if meta.get("kind") == "bundle" else [None]
    return path, meta, [H3RefMod.load(str(path.with_suffix("")), member=i) for i in indices]


def mod_metadata(mod):
    # Do not dataclass-asdict the tensor: that would clone the entire latent.
    result = {key: value for key, value in vars(mod).items() if key not in ("latent", "path")}
    result["refmod_config"] = json.dumps(result.pop("config", {}))
    return result


def save_members(target, mods, settings):
    if not mods: raise ValueError("A RefMod needs at least one appearance or audio reference.")
    rows = [mod_metadata(mod) for mod in mods]
    bundle = len(mods) > 1 or settings.get("preserve_bundle", False)
    meta = {"format_version": 5, "kind": "bundle", "members": rows} if bundle else rows[0]
    meta["skeba_studio"] = settings
    tensors = {f"ref_{i}" if bundle else "latent": mod.latent.detach().cpu().contiguous() for i, mod in enumerate(mods)}
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name("." + target.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        save_file(tensors, str(temp), metadata={"refmod_meta": json.dumps(meta)})
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def _trimmed_source(item):
    path = source_path(item["file"])
    kind = "audio" if item.get("soundtrack_only") else SOURCE_EXTENSIONS[path.suffix.lower()]
    start = float(item.get("start", 0)); end = float(item.get("end", 0))
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or (end and end <= start):
        raise ValueError("Source trim must have a nonnegative start and an end after start (0 means full length).")
    if kind == "image": return kind, load_image(path)[:1]
    if kind == "video":
        frames, _ = load_video(path, 24, 2048)
        frames = frames[int(start*24):int(end*24) if end else None]
        if not len(frames): raise ValueError("Video trim contains no frames.")
        if item.get("mirror"):
            frames = frames.flip(2)
        crop = item.get("crop")
        if crop:
            x,y,w,h = (float(crop[key]) for key in ("x","y","w","h"))
            if not all(math.isfinite(v) for v in (x,y,w,h)) or min(x,y)<0 or min(w,h)<=0 or x+w>1.00001 or y+h>1.00001:
                raise ValueError("Video crop must be inside the frame.")
            height,width=frames.shape[1:3]
            left,top=min(width-1,int(x*width)),min(height-1,int(y*height))
            frames=frames[:,top:max(top+1,min(height,round((y+h)*height))),left:max(left+1,min(width,round((x+w)*width)))].clone()
        return kind, frames
    audio = load_audio(path)
    audio = {**audio, "waveform": audio["waveform"][..., int(start*audio["sample_rate"]):int(end*audio["sample_rate"]) if end else None]}
    if not audio["waveform"].shape[-1]: raise ValueError("Audio trim contains no samples.")
    return kind, audio


def append_look(vae, old, sources, settings, progress=None):
    parts = [old.latent]; first = None
    for index, (frames, video) in enumerate(sources):
        mm.throw_exception_if_processing_interrupted()
        frames = frames[:snap_to_h3_grid(min(len(frames), settings["video_frames"]))] if video else frames[:1]
        pixels = ensure_min_size(_cover(frames, old.latent_w*16, old.latent_h*16))
        if first is None: first = pixels[0].cpu()
        z = vae.encode(pixels)
        if z.ndim != 5 or z.shape[1] != 24:
            raise ValueError("Select the H3 video VAE for appearance sources.")
        if old.mode == "training":
            small = pool_latent(z, z.shape[2], old.latent_h, old.latent_w)
            z = optimize_latent(small, z, steps=settings["steps"],
                                progress=(lambda step, total: progress((index + step / total) / len(sources))) if progress else None)
        elif z.shape[3:] != old.latent.shape[3:]:
            raise ValueError("This reference canvas cannot be appended with the selected VAE. Choose replace appearance instead.")
        parts.append(z.detach().cpu().to(old.latent.dtype))
        if progress: progress((index + 1) / len(sources))
    latent = torch.cat(parts, dim=2)
    return latent, first


class SkebaRefModStudio:
    CATEGORY = "Skeba AI Nodes - Reference"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("saved_file",)
    FUNCTION = "save"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"spec": ("STRING", {"multiline": True, "default": "{}"})},
                "optional": {"vae": ("VAE",), "audio_vae": ("VAE",)}}

    @classmethod
    def IS_CHANGED(cls, **kwargs): return float("nan")

    def save(self, spec, vae=None, audio_vae=None):
        settings = json.loads(spec)
        mode = settings.get("mode", "training")
        if mode not in ("training", "encode"): raise ValueError("Unknown RefMod mode.")
        settings = {"resolution": 1024, "grid": 16, "video_frames": 22, "steps": 500, "audio_seconds": 30,
                    "audio_action": "keep", "appearance_action": "append", **settings}
        for key in ("resolution", "grid", "video_frames", "steps"):
            settings[key] = int(settings[key])
            if settings[key] < (0 if key == "steps" else 1): raise ValueError(key + " is out of range.")
        seconds = float(settings["audio_seconds"])
        if not math.isfinite(seconds) or seconds <= 0: raise ValueError("Audio duration must be positive.")
        if settings["appearance_action"] not in ("append", "replace"): raise ValueError("Unknown appearance action.")
        if settings["audio_action"] not in ("keep", "replace", "append", "remove"): raise ValueError("Unknown audio action.")
        existing = settings.get("existing")
        original_path = None; mods = []; source_meta = {}
        if existing:
            original_path, source_meta, mods = members_from_file(existing)
        companion = settings.get("companion")
        if companion:
            companion_path, _, extra = members_from_file(companion)
            if len(mods)!=1 or len(extra)!=1 or mods[0].kind=="audio" or extra[0].kind!="audio":
                raise ValueError("Paired editing requires one visual file and one audio file.")
            mods.extend(extra)
        output_name = settings["file"]
        if companion and settings.get("overwrite"):
            output_name = str(Path(existing["file"]).with_name(re.sub(r"_(visual|video)$", "", Path(existing["file"]).stem, flags=re.IGNORECASE)+".safetensors"))
        target, relative = output_path(output_name)
        if settings.get("overwrite") and not companion:
            if original_path is None: raise ValueError("Select an existing RefMod before replacing it.")
            target = original_path; relative = existing["file"]
        elif target.exists():
            raise ValueError("That file already exists. Choose another name or select Replace selected file.")
        old_count = len(mods)
        selected = existing.get("member") if existing else None
        visual_i = next((i for i, m in enumerate(mods) if m.kind != "audio"), None)
        audio_i = next((i for i, m in enumerate(mods) if m.kind == "audio"), None)
        if selected is not None:
            if mods[selected].kind == "audio": audio_i = selected
            else: visual_i = selected
        looks = []; voices = []
        for source in settings.get("sources", []):
            sections=source.get("sections")
            if sections is not None and (not isinstance(sections,list) or not sections):
                raise ValueError("Choose at least one video section.")
            for section in sections if sections is not None else [{}]:
                item={**source, **{key:section[key] for key in ("start","end","crop","mirror") if key in section}}
                kind, data = _trimmed_source(item)
                if kind == "audio": voices.append(data)
                else:
                    looks.append((data, kind == "video"))
                    if kind == "video" and source.get("include_audio"):
                        _, soundtrack = _trimmed_source({**item, "soundtrack_only": True})
                        voices.append(soundtrack)
        if looks and vae is None: raise ValueError("Select the H3 video VAE for images and video.")
        if voices and audio_vae is None: raise ValueError("Select the H3 audio VAE for audio.")
        progress = comfy.utils.ProgressBar(100)
        preview = None; name = settings.get("name") or Path(relative).stem
        old = mods[visual_i] if visual_i is not None else None
        order = settings.get("frame_order")
        if order is None and settings.get("frames", "").strip():
            order = [int(v.strip()) for v in settings["frames"].split(",")]
        if old is not None and order is not None:
            if not isinstance(order, list) or any(type(i) is not int or i < 0 or i >= old.latent_t for i in order):
                raise ValueError("Stored frame index is outside this RefMod.")
            if order:
                latent = old.latent[:, :, order].clone()
                old = H3RefMod(**{**vars(old), "latent": latent, "kind": "image" if len(order)==1 else "video"})
                mods[visual_i] = old
            elif looks:
                old = None
            else:
                if settings.get("overwrite") and visual_i != len(mods)-1:
                    raise ValueError("Save as a copy to remove appearance without renumbering attached members.")
                mods.pop(visual_i)
                if audio_i is not None and audio_i > visual_i: audio_i -= 1
                old = None; visual_i = None
        if old is not None and settings.get("retrain"):
            if mode != "training":
                raise ValueError("Choose Compressed mode to refine stored frames, or add original sources to replace them with a full encode.")
            height, width = aspect_grid(settings["grid"], old.latent_h / old.latent_w)
            latent = pool_latent(old.latent, old.latent_t, height, width)
            latent = optimize_latent(latent, old.latent, steps=settings["steps"])
            old = H3RefMod(**{**vars(old), "latent": latent, "mode": "training", "optimize_steps": settings["steps"], "pool": f"{old.latent_t}x{height}x{width}"})
            mods[visual_i] = old
        if looks:
            if old is not None and settings["appearance_action"] == "append":
                latent, preview = append_look(vae, old, looks, settings, progress=lambda value: progress.update_absolute(int(value * 75)))
                new = H3RefMod(**{**vars(old), "latent": latent, "kind": "video" if latent.shape[2]>1 else "image"})
            else:
                latent, info = encode_look(vae, looks, mode=mode, ref_resolution=settings["resolution"], grid=settings["grid"],
                    latent_frames=settings["video_frames"], steps=settings["steps"], label=name, progress=lambda value: progress.update_absolute(int(value * 75)))
                preview = info["first_frame"]
                new = H3RefMod(name=name, kind="video" if latent.shape[2]>1 else "image", latent=latent, mode=mode,
                               source_shape=info["source_shape"], pool=info["pool"], optimize_steps=settings["steps"] if mode=="training" else 0)
            if visual_i is None: mods.append(new); visual_i=len(mods)-1
            else: mods[visual_i]=new
        if voices:
            if audio_i is not None and settings["audio_action"] == "keep":
                raise ValueError("Choose Replace or Append audio to use the uploaded audio clips.")
            if settings["audio_action"] == "remove": raise ValueError("Remove audio conflicts with uploaded audio clips.")
            audio = join_audio(voices)
            waveform = audio["waveform"][..., :int(seconds*audio["sample_rate"])]
            if not waveform.shape[-1]: raise ValueError("Audio duration leaves no samples to encode.")
            parts=[]
            hop=800
            waveform=torch.nn.functional.pad(waveform,(0,(-waveform.shape[-1])%hop))
            for start in range(0,waveform.shape[-1],320000):
                mm.throw_exception_if_processing_interrupted()
                z,_=h3._encode_ref_audio(audio_vae,{"waveform":waveform[...,start:start+320000],"sample_rate":32000})
                parts.append(z.detach().cpu())
            latent=torch.cat(parts,dim=-1)
            if audio_i is not None and settings["audio_action"] == "append": latent=torch.cat([mods[audio_i].latent,latent],dim=-1)
            new=H3RefMod(name=name+" voice",kind="audio",latent=latent,mode="encode")
            if audio_i is None: mods.append(new); audio_i=len(mods)-1
            else: mods[audio_i]=new
        elif settings["audio_action"] == "remove" and audio_i is not None:
            if settings.get("overwrite") and audio_i != len(mods)-1:
                raise ValueError("Save a new file to remove this member without renumbering attached references.")
            mods.pop(audio_i)
        if mods:
            mods[selected if selected is not None and selected < len(mods) else 0].name = name
        for mod in mods:
            mod.description=settings.get("description",mod.description)
            mod.subject_name=settings.get("subject_name",mod.subject_name)
            if mod.kind == "audio": mod.voice_description=settings.get("voice_description",mod.voice_description)
            else: mod.appearance=settings.get("appearance",mod.appearance)
        if settings.get("overwrite") and old_count==1 and len(mods)>1:
            raise ValueError("Adding a second channel changes a standalone file into a bundle. Save a new file, then select its members on the character.")
        progress.update_absolute(95)
        save_members(target,mods,{**source_meta.get("skeba_studio",{}),**settings, "preserve_bundle": source_meta.get("kind")=="bundle"})
        if preview is not None:
            Image.fromarray((preview.detach().cpu().clamp(0,1).numpy()*255).astype("uint8")).save(target.with_suffix(".png"))
        elif original_path is not None and original_path != target:
            for extension in (".png", ".jpg", ".webp"):
                source_preview = original_path.with_suffix(extension)
                if source_preview.is_file():
                    shutil.copyfile(source_preview, target.with_suffix(extension))
                    break
        progress.update_absolute(100)
        return {"ui":{"text":[relative]},"result":(relative,)}
