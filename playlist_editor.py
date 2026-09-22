"""Nondestructive playlist edits and registered single-clip redo workflows."""
import copy
import json
import math
import re
import uuid
from pathlib import Path

import av
import torch
import folder_paths
from comfy_api.latest import InputImpl, Types
from comfy_extras.nodes_audio import load as load_audio
from .playlist_sections import section_edit, context_window, adopt_timeline, assemble_section
from .disk_video import (_MANIFEST_LOCK, playlist_manifest, playlist_media, write_project,
                         _write_clip, _clip_metadata)


class RevisionConflict(ValueError):
    pass


def edit_timeline(token, payload):
    with _MANIFEST_LOCK:
        directory,doc=playlist_manifest(token)
        if payload.get("revision")!=doc["revision"]:
            raise RevisionConflict("Project changed. Refresh and retry your edit.")
        action=payload.get("action","set")
        if action == "delete":
            clip_id = payload.get("clip_id")
            path = playlist_media(token, clip_id)
            for job in doc["jobs"]:
                spec = job["spec"]
                used = {spec["parent_clip_id"]} | {n["clip_id"] for n in spec.get("neighbors", {}).values()}
                if job["state"] in ("prepared", "queued", "running") and clip_id in used:
                    raise ValueError("This clip is used by an active generation. Wait for it to finish or cancel it first.")
            original = copy.deepcopy(doc)
            doc["clips"] = [c for c in doc["clips"] if c["clip_id"] != clip_id]
            doc["timeline"] = [e for e in doc["timeline"] if e["clip_id"] != clip_id]
            for history in ("undo", "redo"):
                doc[history] = [[e for e in entries if e["clip_id"] != clip_id] for entries in doc[history]]
            doc["revision"] += 1
            write_project(directory, doc)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                write_project(directory, original)
                raise ValueError("Could not delete the clip file. Close any external player using it and try again.")
            return doc
        if action in ("undo","redo"):
            other="redo" if action=="undo" else "undo"
            if doc[action]:
                doc[other].append(copy.deepcopy(doc["timeline"]))
                doc["timeline"]=doc[action].pop()
        else:
            timeline=adopt_timeline(doc, payload.get("clip_id")) if action == "adopt" else payload.get("timeline")
            valid={c["clip_id"] for c in doc["clips"]}
            if not isinstance(timeline,list) or any(not isinstance(e,dict) or e.get("clip_id") not in valid or not isinstance(e.get("id"),str) for e in timeline):
                raise ValueError("Timeline contains an unknown clip.")
            if len({e["id"] for e in timeline})!=len(timeline):
                raise ValueError("Timeline entry IDs must be unique.")
            doc["undo"].append(copy.deepcopy(doc["timeline"]))
            doc["undo"]=doc["undo"][-100:];doc["redo"]=[]
            doc["timeline"]=[{"id":e["id"],"clip_id":e["clip_id"]} for e in timeline]
        doc["revision"]+=1;write_project(directory,doc)
        return doc


def template_root():
    return Path(folder_paths.get_user_directory())/"h3_playlist_templates"


def templates():
    root=template_root()
    return [{"id":p.stem,"name":json.loads(p.read_text(encoding="utf-8"))["name"]}
            for p in sorted(root.glob("*.json"))] if root.exists() else []


def read_template(identifier):
    if not re.fullmatch(r"[a-f0-9]{32}",identifier or ""):
        raise ValueError("Select a registered redo workflow.")
    return json.loads((template_root()/(identifier+".json")).read_text(encoding="utf-8"))


def default_redo_crf(inputs):
    # Older frontend exports stored a blank quality widget as JSON null.
    if inputs.get("crf") is None:
        inputs["crf"] = 18


def register_template(name,graph):
    if not isinstance(graph,dict) or not graph:
        raise ValueError("Export an executable ComfyUI workflow.")
    if any(not isinstance(n,dict) or not n.get("class_type") for n in graph.values()):
        raise ValueError("Workflow has missing node definitions. Restart ComfyUI, reload the redo workflow and register again.")
    outputs=[key for key,n in graph.items() if n.get("class_type")=="SkebaPlaylistRedoSave"]
    if len(outputs)!=1:raise ValueError("Workflow needs exactly one Playlist Redo Save node.")
    reachable=set()
    def visit(key):
        if key in reachable:return
        if key not in graph:raise ValueError("Workflow has an unresolved input connection.")
        reachable.add(key)
        for value in graph[key].get("inputs",{}).values():
            if isinstance(value,list) and len(value)==2 and isinstance(value[1],int):visit(str(value[0]))
    visit(outputs[0]);graph={k:copy.deepcopy(v) for k,v in graph.items() if k in reachable}
    inputs=[k for k,n in graph.items() if n.get("class_type")=="SkebaPlaylistRedoInput"]
    connectors=[k for k,n in graph.items() if n.get("class_type")=="SkebaMiniMaxH3AVConnectorGuideTest"]
    if len(inputs)!=1 or len(connectors)!=2:
        raise ValueError("Redo workflow needs one Playlist Redo Input and two AV Connector passes.")
    marker = inputs[0]
    references = [n for n in graph.values() if n.get("class_type") == "SkebaCachedMiniMaxH3ReferenceFirstLast"]
    compilers = [n for n in graph.values() if n.get("class_type") == "H3TaggedReferencePrompt"]
    noise = [n for n in graph.values() if n.get("class_type") == "RandomNoise"]
    finalizers = [k for k,n in graph.items() if n.get("class_type") == "SkebaH3AVConnectorFinalizeTest"]
    if len(references) != 2 or any(n["inputs"].get("length") != [marker,2] for n in references):
        raise ValueError("Connect Redo Input generation_length to both Cached Reference passes.")
    if not compilers or any(n["inputs"].get("prompt_template") != [marker,1] for n in compilers):
        raise ValueError("Connect Redo Input prompt to the Tagged Reference Prompt compiler.")
    if not noise or any(n["inputs"].get("noise_seed") != [marker,3] for n in noise):
        raise ValueError("Connect Redo Input seed to every RandomNoise node used by the redo.")
    saved = graph[outputs[0]]["inputs"]
    default_redo_crf(saved)
    if len(finalizers) != 1 or saved.get("images") != [finalizers[0],0] or ("audio" in saved and saved["audio"] != [finalizers[0],1]):
        raise ValueError("Connect AV Connector Finalize images/audio to Redo Save so hidden overlaps are removed.")
    bundle = graph[finalizers[0]]["inputs"].get("connector_bundle")
    if not isinstance(bundle,list) or bundle[0] not in connectors or bundle[1] != 1 or graph[bundle[0]]["inputs"].get("preserve_upscaled_endpoints") is not True:
        raise ValueError("Finalize must use the upscale connector bundle with preserve_upscaled_endpoints enabled.")
    forbidden=("ForLoop", "SkebaSaveClipToFile", "MotionContext", "SkebaCompilePlaylist", "SkebaFinishPlaylist")
    if any(any(t in n.get("class_type","") for t in forbidden) for n in graph.values()):
        raise ValueError("Redo graph must be a single clip: remove loop, Motion Context, context saves and final assembly dependencies.")
    identifier=uuid.uuid4().hex
    data={"name":str(name).strip() or "H3 two-pass redo","graph":graph,"input":inputs[0],"output":outputs[0],"connectors":connectors}
    root=template_root();root.mkdir(parents=True,exist_ok=True)
    (root/(identifier+".json")).write_text(json.dumps(data,indent=2),encoding="utf-8")
    return {"id":identifier,"name":data["name"]}


def timing(duration,previous_frames=0,next_frames=0):
    seconds=float(duration)
    if not math.isfinite(seconds) or seconds<=0:raise ValueError("Duration must be positive.")
    visible=max(1,round(seconds*24))
    total=max(5,visible+previous_frames+next_frames)
    generation=total+(5-total%17)%17
    return visible,generation


def prepare_redo(token,payload):
    template=read_template(payload.get("template"))
    with _MANIFEST_LOCK:
        directory,doc=playlist_manifest(token)
        if payload.get("revision")!=doc["revision"]:raise RevisionConflict("Timeline changed. Reopen Redo to confirm its neighbors.")
        timeline=doc["timeline"];index=next((i for i,e in enumerate(timeline) if e["id"]==payload.get("entry_id")),None)
        if index is None:raise ValueError("Select an active timeline clip to redo.")
        current=next(c for c in doc["clips"] if c["clip_id"]==timeline[index]["clip_id"])
        edit = section_edit(doc, index, payload)
        prompt=payload.get("prompt", "" if edit else current.get("prompt",""))
        if not isinstance(prompt,str) or not prompt.strip():raise ValueError("Enter the clip prompt.")
        seed=int(payload.get("seed",0))
        if not 0<=seed<=2**53-1:raise ValueError("Seed must be a nonnegative safe integer.")
        spec={"project":token,"parent_clip_id":current["clip_id"],"prompt":prompt,"seed":seed,
              "template":payload["template"],"template_name":template["name"],"neighbors":{}}
        if edit:
            spec["edit"] = edit
        for side in ("previous", "next"):
            choice = payload.get(side) or {}
            if not choice.get("enabled", bool(edit)):
                continue
            window = context_window(doc, index, side, edit)
            if not window:
                if edit: continue
                raise ValueError(f"No {side} clip is available.")
            neighbor, low, high = window
            requested = int(choice.get("frames", 22))
            if requested not in (5,22,39,56):
                raise ValueError("Context frames must be 5, 22, 39 or 56.")
            fits = [n for n in (5,22,39,56) if n <= requested and n/24 <= high-low+1e-7]
            if not fits:
                if edit: continue
                raise ValueError(f"The {side} clip is shorter than {requested} frames.")
            frames = max(fits) if edit else requested
            if not edit and requested/24 > high-low+1e-7:
                raise ValueError(f"The {side} clip is shorter than {requested} frames.")
            path = playlist_media(token, neighbor["clip_id"])
            with av.open(str(path)) as container:
                has_audio = bool(container.streams.audio)
            spec["neighbors"][side] = {"clip_id":neighbor["clip_id"], "frames":frames,
                "audio":bool(choice.get("audio",True)) and has_audio,
                "start_seconds":high-frames/24 if side == "previous" else low}
        default_duration = ((edit["end_frame"]-edit["start_frame"])/current["fps"]
                            if edit and edit["mode"] == "replace" else 5 if edit else current["duration_seconds"])
        visible,generation=timing(payload.get("duration",default_duration),
            spec["neighbors"].get("previous",{}).get("frames",0),spec["neighbors"].get("next",{}).get("frames",0))
        spec.update(visible_frames=visible,generation_length=generation,duration=visible/24)
        spec["prompt"]=re.sub(r"\[s\s*=\s*[\d.]+\]",f"[s={visible/24:g}]",prompt,flags=re.I)
        request_id=uuid.uuid4().hex;spec["request_id"]=request_id
        graph=copy.deepcopy(template["graph"])
        default_redo_crf(graph[template["output"]]["inputs"])
        graph[template["input"]]["inputs"]={"request":json.dumps(spec)}
        graph[template["output"]]["inputs"]["request"]=[template["input"],0]
        for key in template["connectors"]:
            inputs=graph[key]["inputs"];inputs["bypass"]=not bool(spec["neighbors"])
            for side,prefix,slots in (("previous","start",(4,5)),("next","end",(6,7))):
                selected=spec["neighbors"].get(side)
                inputs.pop(prefix+"_frames",None);inputs.pop(prefix+"_audio",None)
                if selected:
                    inputs[prefix+"_overlap"]=str(selected["frames"])
                    inputs[prefix+"_frames"]=[template["input"],slots[0]]
                    if selected["audio"]:inputs[prefix+"_audio"]=[template["input"],slots[1]]
        doc["redo_template"]=payload["template"]
        prompt_id=str(uuid.uuid4())
        doc["jobs"].append({"id":request_id,"prompt_id":prompt_id,"state":"prepared","spec":spec,"output_node":template["output"]})
        write_project(directory,doc)
    return {"request_id":request_id,"prompt_id":prompt_id,"graph":graph,"duration":visible/24}


def update_job(token,identifier,changes):
    with _MANIFEST_LOCK:
        directory,doc=playlist_manifest(token)
        job=next((j for j in doc["jobs"] if j["id"]==identifier),None)
        if job is None:raise ValueError("Unknown redo job.")
        if "state" in changes and changes["state"] not in ("prepared", "queued", "running", "failed", "canceled"):
            raise ValueError("Invalid job state.")
        if "prompt_id" in changes and changes["prompt_id"] != job.get("prompt_id"):
            raise ValueError("Queue ID does not match the saved redo request.")
        if job.get("state")!="completed":
            for key in ("prompt_id","state","error"):
                if key in changes:job[key]=changes[key]
            write_project(directory,doc)
        return job


def neighbor_media(spec,side):
    selected=spec["neighbors"].get(side)
    if not selected:return None,None
    path=playlist_media(spec["project"],selected["clip_id"])
    _,doc=playlist_manifest(spec["project"])
    metadata=next(c for c in doc["clips"] if c["clip_id"]==selected["clip_id"])
    count=selected["frames"];start=max(0,metadata["duration_seconds"]-count/24) if side=="previous" else 0
    start = selected.get("start_seconds", start)
    images=[]
    with av.open(str(path)) as container:
        stream=container.streams.video[0];origin=float(stream.start_time or 0)*float(stream.time_base)
        if start:container.seek(int((start+origin)/float(stream.time_base)),stream=stream,backward=True)
        previous = None
        target = start
        for frame in container.decode(stream):
            if frame.time is None: continue
            stamp = float(frame.time)-origin
            pixels = torch.from_numpy(frame.to_ndarray(format="rgb24")).float()/255
            while previous is not None and target < stamp-1e-7 and len(images) < count:
                images.append(previous)
                target = start+len(images)/24
            previous = pixels
            if len(images) == count: break
        while previous is not None and len(images) < count and target < metadata["duration_seconds"]-1e-7:
            images.append(previous)
            target = start+len(images)/24
    if len(images)!=count:raise ValueError(f"Cannot decode {count} frames from {side} clip.")
    audio=None
    if selected["audio"]:
        waveform,rate=load_audio(str(path));begin=round(start*rate);end=begin+round(count/24*rate)
        if waveform.shape[-1]<end:raise ValueError(f"{side} soundtrack is too short for the selected context.")
        audio={"waveform":waveform[:,begin:end].unsqueeze(0).clone(),"sample_rate":rate}
    return torch.stack(images),audio


class PlaylistRedoInput:
    @classmethod
    def INPUT_TYPES(cls):return {"required":{"request":("STRING",{"default":"{}","multiline":True})}}
    RETURN_TYPES=("STRING","STRING","INT","INT","IMAGE","AUDIO","IMAGE","AUDIO")
    RETURN_NAMES=("request","prompt","generation_length","seed","previous_frames","previous_audio","next_frames","next_audio")
    FUNCTION="load"
    CATEGORY="Skeba AI Nodes - Utilities/Playlist"
    def load(self,request):
        spec=json.loads(request)
        verify_request(spec)
        update_job(spec["project"],spec["request_id"],{"state":"running"})
        previous,pa=neighbor_media(spec,"previous");following,fa=neighbor_media(spec,"next")
        return request,generation_prompt(spec),spec["generation_length"],spec["seed"],previous,pa,following,fa


class PlaylistRedoSave:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"images":("IMAGE",),"request":("STRING",{"forceInput":True}),"crf":("INT",{"default":18,"min":0,"max":51})},"optional":{"audio":("AUDIO",)}}
    RETURN_TYPES=("STRING",)
    FUNCTION="save"
    OUTPUT_NODE=True
    CATEGORY="Skeba AI Nodes - Utilities/Playlist"
    def save(self,images,request,crf=18,audio=None):
        spec=json.loads(request);token=spec["project"]
        directory,doc=playlist_manifest(token)
        job=verify_request(spec)
        if job.get("state")=="completed":return {"ui":{"text":[job["clip_id"]]},"result":(job["clip_id"],)}
        count=spec["visible_frames"]
        if len(images)<count:raise ValueError("Redo output is shorter than the requested duration.")
        images=images[:count]
        if audio:
            rate=audio["sample_rate"];samples=round(count/24*rate);waveform=audio["waveform"]
            if waveform.shape[-1]<samples:raise ValueError("Redo audio is shorter than the requested duration.")
            audio={"waveform":waveform[...,:samples],"sample_rate":rate}
        path=directory/("redo_"+spec["request_id"]+".mp4")
        video=InputImpl.VideoFromComponents(Types.VideoComponents(images=images,audio=audio,frame_rate=24))
        output = path
        try:
            _write_clip(video,path,crf=crf)
            if spec.get("edit"):
                output = directory/("edited_"+spec["request_id"]+".mp4")
                expected = assemble_section(spec, path, output, crf)
                if _clip_metadata(output)["frame_count"] != expected:
                    raise ValueError("Assembled frame count does not match the requested edit.")
            with _MANIFEST_LOCK:
                verify_request(spec)
                directory,doc=playlist_manifest(token)
                records = []
                if spec.get("edit"):
                    records.append({**_clip_metadata(path), "clip_id":path.stem,
                                    "media_role":"generated_section", "parent_clip_id":spec["parent_clip_id"],
                                    "prompt":spec["prompt"], "redo":spec})
                records.append({**_clip_metadata(output), "clip_id":output.stem,
                    "media_role":"alternate", "parent_clip_id":spec["parent_clip_id"],
                    "prompt":spec["prompt"], "redo":spec})
                for record in records:
                    record["index"] = len(doc["clips"])+1
                    doc["clips"].append(record)
                doc["revision"]+=1
                job=next(j for j in doc["jobs"] if j["id"]==spec["request_id"])
                job.update(state="completed",clip_id=output.stem)
                write_project(directory,doc)
        except BaseException:
            output.unlink(missing_ok=True)
            path.unlink(missing_ok=True)
            raise
        return {"ui":{"text":[output.stem],"skeba_playlist":[token]},"result":(output.stem,)}



def verify_request(spec):
    if "request_id" not in spec:
        raise ValueError("Register this workflow, then use Redo in H3 Live Playlist.")
    _, doc = playlist_manifest(spec["project"])
    job = next((j for j in doc["jobs"] if j["id"] == spec["request_id"]), None)
    if job is None or job["spec"] != spec:
        raise ValueError("Redo request does not match its saved project job.")
    if job["state"] == "canceled":
        raise ValueError("This redo was canceled. Submit a new redo from the playlist.")
    return job


def reconcile_jobs(token, queue):
    with _MANIFEST_LOCK:
        directory, doc = playlist_manifest(token)
        running, pending = queue.get_current_queue()
        running_ids = {row[1] for row in running}
        pending_ids = {row[1] for row in pending}
        changed = False
        for job in doc["jobs"]:
            identifier = job.get("prompt_id")
            if not identifier or job["state"] in ("completed", "failed", "canceled"):
                continue
            before = dict(job)
            run = queue.get_history(prompt_id=identifier).get(identifier)
            if run:
                messages = run.get("status", {}).get("messages", [])
                error = next((m[1].get("exception_message") for m in messages if m[0] == "execution_error"), None)
                interrupted = any(m[0] == "execution_interrupted" for m in messages)
                job.update(state="canceled" if interrupted else "failed",
                           error=error or "Workflow finished without saving an alternate clip.")
            elif identifier in running_ids:
                job["state"] = "running"
            elif identifier in pending_ids:
                job["state"] = "queued"
            elif job["state"] == "prepared":
                continue
            else:
                job.update(state="canceled", error="Job is no longer in the ComfyUI queue (removed or server restarted).")
            changed = changed or job != before
        if changed:
            write_project(directory, doc)
        return directory, doc


def generation_prompt(spec):
    # Saved authoring times describe visible output; guided frames are hidden.
    head = spec["neighbors"].get("previous", {}).get("frames", 0) / 24
    prompt = spec["prompt"]
    if head:
        def shift(match):
            seconds = int(match[2]) * 60 + float(match[3]) + head
            return f"{match[1]}{int(seconds // 60):02}:{seconds % 60:06.3f}"
        prompt = re.sub(r"(\[Shot[^\]]*\]\s*At\s+)(\d+):(\d+(?:\.\d+)?)", shift, prompt, flags=re.I)
    return re.sub(r"\[s\s*=\s*[\d.]+\]", f"[s={spec['generation_length']/24:g}]", prompt, flags=re.I)
