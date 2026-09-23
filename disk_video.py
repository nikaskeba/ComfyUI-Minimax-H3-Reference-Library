"""File-backed loop clips; only the current clip is decoded in memory."""

from collections import deque
from datetime import datetime
from fractions import Fraction
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import uuid
import wave
import threading

import av
import numpy as np
import torch
import torchaudio
import folder_paths
from .playlist_timeline import frame_range, render_timeline
from comfy_api.latest import InputImpl


def _ffmpeg():
    executable = shutil.which("ffmpeg")
    if executable is None:
        raise RuntimeError("Skeba disk video requires ffmpeg on PATH.")
    return executable


def playlist_projects():
    path = Path(folder_paths.get_user_directory()) / "h3_video_projects.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def register_playlist(directory):
    directory = directory.resolve()
    projects = playlist_projects()
    for token, location in projects.items():
        if location == str(directory):
            return token
    token = uuid.uuid4().hex
    projects[token] = str(directory)
    path = Path(folder_paths.get_user_directory()) / "h3_video_projects.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(projects, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return token


def playlist_manifest(token):
    location = playlist_projects().get(token)
    if location is None:
        raise FileNotFoundError("Unknown video project")
    directory = Path(location).resolve()
    return directory, normalize_project(json.loads((directory / "manifest.json").read_text(encoding="utf-8")))


def playlist_media(token, clip_id):
    directory, manifest = playlist_manifest(token)
    entry = next((entry for entry in manifest["clips"] if entry["clip_id"] == clip_id), None)
    if entry is None:
        raise FileNotFoundError("Unknown clip")
    path = (directory / entry["filename"]).resolve()
    if path.parent != directory or path.suffix.lower() != ".mp4":
        raise ValueError("Invalid clip path")
    return path


class DiskClip(InputImpl.VideoFromFile):
    def seam_frames(self, count):
        # Seek near the end, retaining only the requested tail frames.
        with av.open(self.get_stream_source()) as container:
            stream = container.streams.video[0]
            duration = float(container.duration or 0) / av.time_base
            container.seek(int(max(0, duration - 2) / stream.time_base), stream=stream)
            frames = deque(maxlen=count)
            for frame in container.decode(stream):
                frames.append(frame.to_ndarray(format="rgb24"))
        return torch.from_numpy(np.stack(frames)).float().div_(255)


def _geometry(path):
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        return stream.width, stream.height, stream.average_rate


def _clip_metadata(path):
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        fps = stream.average_rate
        frames = stream.frames
        if not frames:
            frames = sum(1 for packet in container.demux(stream) if packet.size)
        return {"filename": path.name, "frame_count": frames, "fps": float(fps),
                "fps_fraction": str(fps), "duration_seconds": float(Fraction(frames, 1) / fps),
                "width": stream.width, "height": stream.height}


_MANIFEST_LOCK = threading.RLock()

def normalize_project(document):
    counts=document.setdefault("clip_label_counts",{})
    for clip in document.get("clips",[]):
        if clip.get('redo',{}).get('edit',{}).get('mode')=='insert_between' and clip.get('media_role')!='generated_section':
            clip['media_role']='new_clip'
            if clip.get('display_name','').startswith('Redo '):clip.pop('display_name',None)
        kind="Import" if clip.get("media_role")=="imported" else "Redo" if clip.get("parent_clip_id") and clip.get('media_role')!='new_clip' else "Clip"
        if not clip.get("display_name"):
            counts[kind]=counts.get(kind,0)+1
            clip["display_name"]=f"{kind} {counts[kind]}"
    known={c['clip_id']:c for c in document.get('clips',[])}
    edit_counts=document.setdefault('edit_label_counts',{})
    for clip in document.get('clips',[]):
        if clip.get('redo',{}).get('edit',{}).get('mode')=='insert_between' and clip.get('media_role')!='generated_section':
            clip['media_role']='new_clip'
        if not clip.get('parent_clip_id') or clip.get('media_role')=='new_clip':
            continue
        if not clip.get('edit_display_name'):
            root=known.get(clip['parent_clip_id']);seen={clip['clip_id']}
            while root and root.get('parent_clip_id') and root.get('media_role')!='new_clip' and root['clip_id'] not in seen:
                seen.add(root['clip_id']);parent=known.get(root['parent_clip_id'])
                if not parent:break
                root=parent
            root_id=(root or {}).get('edit_root_id',(root or {}).get('clip_id',clip['parent_clip_id']))
            root_name=(root or {}).get('edit_root_name',(root or {}).get('display_name','Clip'))
            edit_counts[root_id]=edit_counts.get(root_id,0)+1
            clip.update(edit_root_id=root_id,edit_root_name=root_name,edit_display_name=f"{root_name} - Redo {edit_counts[root_id]}")
    document.setdefault("timeline", [{"id":"original_"+c["clip_id"],"clip_id":c["clip_id"]}
                                      for c in document.get("clips",[]) if not c.get("parent_clip_id")])
    document.setdefault("revision",0)
    document.setdefault("undo",[])
    document.setdefault("redo",[])
    document.setdefault("jobs",[])
    document.setdefault("redo_template",None)
    document["schema_version"]=2
    return document


def write_project(directory,document):
    normalize_project(document)
    temporary=directory / f".manifest_{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_text(json.dumps(document,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        temporary.replace(directory/"manifest.json")
    finally:
        temporary.unlink(missing_ok=True)


def _update_manifest(directory, *, clip=None, combined=None):
    with _MANIFEST_LOCK:
        return _update_manifest_locked(directory, clip=clip, combined=combined)

def _update_manifest_locked(directory, *, clip=None, combined=None):
    path = directory / "manifest.json"
    document = (json.loads(path.read_text(encoding="utf-8")) if path.exists()
                else {"schema_version": 1, "clips": [], "combined_videos": []})
    normalize_project(document)
    if clip is not None:
        document["clips"].append(clip)
        if not clip.get("parent_clip_id"):
            entry={"id":uuid.uuid4().hex,"clip_id":clip["clip_id"]}
            document["timeline"].append(entry)
            # Undo of a manual edit must not discard clips arriving from generation.
            for snapshot in document["undo"]+document["redo"]:
                snapshot.append(dict(entry))
        document["revision"]+=1
    if combined is not None:
        document["combined_videos"].append(combined)
    write_project(directory,document)


def _write_clip(video, path, geometry=None, crf=18):
    components = video.get_components()
    images = components.images
    fps = Fraction(components.frame_rate)
    count, height, width, _ = images.shape
    if not count:
        raise ValueError("Cannot save an empty video clip.")
    duration = count / float(fps)
    # Every intermediate has stereo 48 kHz AAC audio, including silence.
    audio = components.audio
    if audio is None:
        waveform = torch.zeros(2, round(duration * 48000))
    else:
        waveform = audio["waveform"]
        if waveform.shape[0] != 1 or waveform.shape[1] not in (1, 2):
            raise ValueError("Disk clips support one audio batch with mono or stereo channels.")
        waveform = waveform[0].detach().cpu()
        if audio["sample_rate"] != 48000:
            waveform = torchaudio.functional.resample(waveform, audio["sample_rate"], 48000)
        if waveform.shape[0] == 1:
            waveform = waveform.repeat(2, 1)
    samples = round(duration * 48000)
    waveform = waveform[:, :samples]
    waveform = torch.nn.functional.pad(waveform, (0, samples - waveform.shape[-1]))
    with tempfile.TemporaryDirectory(dir=path.parent) as temporary:
        wav = Path(temporary) / "audio.wav"
        with wave.open(str(wav), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(48000)
            output.writeframes(waveform.clamp(-1, 1).mul(32767).round().to(torch.int16).t().contiguous().numpy().tobytes())
        command = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                   "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{width}x{height}",
                   "-framerate", str(fps), "-i", "pipe:0", "-i", str(wav),
                   "-map", "0:v:0", "-map", "1:a:0"]
        if geometry is not None:
            target_w, target_h, target_fps = geometry
            command += ["-vf", f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,fps={target_fps}"]
        command += ["-c:v", "libx264", "-preset", "fast", "-crf", str(crf),
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", str(duration), str(path)]
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                for frame in images:
                    process.stdin.write(frame[..., :3].detach().cpu().clamp(0, 1).mul(255).round().to(torch.uint8).contiguous().numpy().tobytes())
                process.stdin.close()
                code = process.wait()
            except BaseException:
                process.kill()
                process.wait()
                raise
            if code:
                errors.seek(0)
                raise RuntimeError("Clip encoding failed: " + errors.read().decode(errors="replace"))
    return DiskClip(str(path))


class SaveClipToFile:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"video": ("VIDEO",), "crf": ("INT", {"default": 18, "min": 0, "max": 51})},
                "optional": {
                    "accumulation": ("ACCUMULATION", {"forceInput": True}),
                    "output_folder": ("STRING", {"default": "skeba_clips", "tooltip": "Folder relative to ComfyUI/output, or an absolute folder path. Blank uses ComfyUI/output."}),
                    "project_name": ("STRING", {"default": "", "tooltip": "Optional project subfolder. Each run creates a dated bundle containing its clips and final video."}),
                    "preview_clip": ("BOOLEAN", {"default": False, "tooltip": "Show each completed clip in the node. Creates a temporary MP4 preview with audio; the loop still uses the saved MP4."}),
                    "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "Optional prompt for this clip. Saved verbatim with its filename and measured duration in manifest.json. Can be connected to the current loop prompt."}),
                    "seed": ("INT", {"forceInput":True}),
                }, "hidden":{"execution_prompt":"PROMPT"}}

    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("video",)
    FUNCTION = "save"
    CATEGORY = "Skeba AI Nodes - Utilities"

    def save(self, video, crf=18, accumulation=None, output_folder="skeba_clips", project_name="", preview_clip=False, prompt="", seed=None, execution_prompt=None):
        clips = (accumulation or {}).get("accum", [])
        if clips and isinstance(clips[-1], DiskClip):
            directory = Path(clips[-1].get_stream_source()).parent
        else:
            project_name = project_name.strip()
            if project_name and (project_name in (".", "..") or
                                 any(c in project_name for c in '<>:"/\\|?*') or
                                 any(ord(c) < 32 for c in project_name) or
                                 project_name.endswith(".")):
                raise ValueError("Project name must be a single folder name without path separators or reserved filename characters.")
            base = Path(output_folder.strip())
            if not base.is_absolute():
                if ".." in base.parts:
                    raise ValueError("Use an absolute output folder instead of '..' in a relative path.")
                base = Path(folder_paths.get_output_directory()) / base
            directory = base / project_name / (datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + "_" + uuid.uuid4().hex[:8])
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"clip_{len(clips) + 1:05}_{uuid.uuid4().hex[:8]}.mp4"
        clip = _write_clip(video, path, crf=crf)
        if seed is None and execution_prompt:
            seeds={n.get('inputs',{}).get('noise_seed') for n in execution_prompt.values()
                   if n.get('class_type')=='RandomNoise' and type(n.get('inputs',{}).get('noise_seed')) is int}
            if len(seeds)==1:seed=seeds.pop()
        _update_manifest(directory, clip={
            **_clip_metadata(path), "clip_id": path.stem, "index": len(clips) + 1,
            "prompt": prompt, "crf": crf, "seed":seed,
            "previous_file": str(Path(clips[-1].get_stream_source()).resolve()) if clips and isinstance(clips[-1], DiskClip) else None,
        })
        ui = {"skeba_playlist": [register_playlist(directory)]}
        if not preview_clip:
            if ui:
                return {"result": (clip,), "ui": ui}
            return (clip,)
        preview_directory = Path(folder_paths.get_temp_directory()) / "skeba_clip_previews"
        preview_directory.mkdir(parents=True, exist_ok=True)
        preview = preview_directory / f"{path.stem}_{uuid.uuid4().hex[:8]}.mp4"
        shutil.copyfile(path, preview)
        return {"result": (clip,), "ui": {
            **ui,
            "skeba_clip_preview": [{"filename": preview.name, "subfolder": "skeba_clip_previews", "type": "temp"}],
        }}


def _join_audio(paths, destination):
    # Decode one audio frame at a time and discard AAC tail padding per clip.
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(48000)
        for path in paths:
            with av.open(str(path)) as container:
                video = container.streams.video[0]
                if video.duration is None:
                    # Earlier MKV intermediates do not always expose stream duration.
                    with av.open(str(path)) as probe:
                        frames = sum(1 for packet in probe.demux(video=0) if packet.size)
                    duration = frames / float(video.average_rate)
                else:
                    duration = float(video.duration * video.time_base)
                remaining = round(duration * 48000)
                resampler = av.AudioResampler(format="s16", layout="stereo", rate=48000)
                for frame in container.decode(audio=0):
                    for converted in resampler.resample(frame):
                        data = converted.to_ndarray().tobytes()
                        count = min(remaining, converted.samples)
                        output.writeframesraw(data[:count * 4])
                        remaining -= count
                    if remaining == 0:
                        break
                for converted in resampler.resample(None):
                    count = min(remaining, converted.samples)
                    output.writeframesraw(converted.to_ndarray().tobytes()[:count * 4])
                    remaining -= count
                while remaining:
                    count = min(remaining, 48000)
                    output.writeframesraw(bytes(count * 4))
                    remaining -= count


def combine_disk_clips(clips, starting_video=None, ending_video=None):
    paths = [Path(clip.get_stream_source()) for clip in clips]
    geometry = _geometry(paths[0])
    if any(_geometry(path) != geometry for path in paths[1:]):
        raise ValueError("Disk clips must have matching dimensions and frame rates.")
    directory = paths[0].parent
    token = uuid.uuid4().hex[:8]
    for label, video in (("start", starting_video), ("end", ending_video)):
        if video is not None:
            path = directory / f"{label}_{token}.mp4"
            _write_clip(video, path, geometry=geometry)
            paths.insert(0, path) if label == "start" else paths.append(path)
    output = directory / f"combined_{token}.mp4"
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        manifest = Path(temporary) / "concat.txt"
        manifest.write_text("".join("file '" + path.resolve().as_posix().replace("'", "'\\''") + "'\n"
                                    for path in paths), encoding="utf-8")
        audio = Path(temporary) / "joined.wav"
        _join_audio(paths, audio)
        result = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                             "-f", "concat", "-safe", "0", "-i", str(manifest),
                             "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
                             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                             "-movflags", "+faststart", str(output)], capture_output=True, text=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError("Clip concatenation failed: " + result.stderr)
    _update_manifest(directory, combined={
        **_clip_metadata(output),
        "clips": [{**_clip_metadata(path),
                   "path": path.name if path.parent == directory else str(path.resolve()),
                   "role": "starting" if starting_video is not None and i == 0 else
                           "ending" if ending_video is not None and i == len(paths) - 1 else "generated"}
                  for i, path in enumerate(paths)],
    })
    return DiskClip(str(output)), len(paths)


class CompilePlaylist:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"project":("STRING",),"clip_ids":("STRING",)}}
    RETURN_TYPES=("STRING",)
    FUNCTION="compile"
    OUTPUT_NODE=True
    CATEGORY="Skeba AI Nodes - Utilities"
    @classmethod
    def IS_CHANGED(cls,**kwargs): return float("nan")
    def compile(self,project,clip_ids):
        ids=json.loads(clip_ids)
        if not isinstance(ids,list) or not ids or not all(isinstance(i,(str,dict)) for i in ids):
            raise ValueError("Choose completed clips to compile.")
        if any(isinstance(i,dict) for i in ids):
            directory,doc=playlist_manifest(project)
            known={c['clip_id']:c for c in doc['clips']}
            entries=[{'clip_id':i} if isinstance(i,str) else i for i in ids]
            pieces=[]
            for entry in entries:
                clip=known.get(entry.get('clip_id'))
                if clip is None:raise ValueError('Unknown timeline clip.')
                frame_range(entry,clip)
                pieces.append((playlist_media(project,clip['clip_id']),clip,entry))
            output=directory/('combined_'+uuid.uuid4().hex[:8]+'.mp4')
            render_timeline(_ffmpeg(),pieces,output)
            _update_manifest(directory,combined={**_clip_metadata(output),'timeline':entries})
            result=DiskClip(str(output))
        else:
            clips=[DiskClip(str(playlist_media(project,i))) for i in ids]
            result,count=combine_disk_clips(clips)
        filename=Path(result.get_stream_source()).name
        return {"ui":{"text":[filename]},"result":(filename,)}


class FinishPlaylist:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"accumulation":("ACCUMULATION",)}}
    RETURN_TYPES=("STRING",)
    FUNCTION="finish"
    OUTPUT_NODE=True
    CATEGORY="Skeba AI Nodes - Utilities"
    def finish(self,accumulation):
        clips=accumulation.get("accum",[])
        if not clips or not all(isinstance(clip,DiskClip) for clip in clips):
            raise ValueError("Connect the completed disk-clip accumulation.")
        token=register_playlist(Path(clips[-1].get_stream_source()).parent)
        return {"ui":{"text":[f"{len(clips)} clips ready. Use Create Video in H3 Live Playlist."],"skeba_playlist":[token]},"result":(token,)}


def playlist_final(token,filename):
    directory,manifest=playlist_manifest(token)
    if not any(entry["filename"]==filename for entry in manifest.get("combined_videos",[])):
        raise FileNotFoundError("Unknown compiled video")
    path=(directory/filename).resolve()
    if path.parent!=directory or path.suffix.lower()!=".mp4":
        raise ValueError("Invalid compiled video path")
    return path
