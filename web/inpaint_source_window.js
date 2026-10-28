import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const FPS = 24;
const VIDEO_MODES = ["audio drives video", "controlnet only", "inpaint only", "controlnet and inpainting"];

function control(node, name) {
    return node?.widgets?.find((widget) => widget.name === name);
}

function plannerFor(node) {
    const linkId = node.inputs?.find((input) => input.name === "start_frame")?.link;
    const link = linkId == null ? null : app.graph.links[linkId];
    return link ? app.graph.getNodeById(link.origin_id) : null;
}

function batchFitFor(node) {
    const planner = plannerFor(node);
    const linkId = planner?.inputs?.find((input) => input.name === "start_frame")?.link;
    const link = linkId == null ? null : app.graph.links[linkId];
    const upstream = link ? app.graph.getNodeById(link.origin_id) : null;
    return upstream?.type === "SkebaH3InpaintBatchFit" ? upstream : null;
}

function sourceControl(node, name) {
    if (name === "start_frame") {
        const selectors = (app.graph?._nodes || []).filter((other) => other.type === "SkebaH3InpaintStartFrame");
        const connected = selectors.find((other) => (other.outputs?.[0]?.links || []).some((id) => {
            const link = app.graph.links[id];
            const target = link && app.graph.getNodeById(link.target_id);
            return target?.inputs?.[link.target_slot]?.name === "source_start_frame";
        }));
        return control(connected, "start_frame") || control(batchFitFor(node), "start_frame") || control(plannerFor(node), "start_frame");
    }
    if (name === "video") {
        const choices = (app.graph?._nodes || []).filter((other) => other.type === "SkebaH3InpaintVideoChoice");
        const connected = choices.find((other) => (other.outputs?.[0]?.links || []).some((id) => {
            const link = app.graph.links[id];
            const target = link && app.graph.getNodeById(link.target_id);
            return target?.inputs?.[link.target_slot]?.name === "source_video";
        }));
        return control(connected, "video") || control(batchFitFor(node), "video") || control(node, "video");
    }
    return control(node, name);
}

function frameField(label, read, write, mediaKind = "video", help = "") {
    const row = document.createElement("div");
    row.style.cssText = "margin:8px 0;padding:8px;border:1px solid #454b57;border-radius:7px;background:#1e232b";
    const heading = document.createElement("div");
    heading.textContent = label;
    heading.style.cssText = "font-weight:600;margin-bottom:5px;color:#d9e4f3";
    if (help) {
        const icon = document.createElement("span");
        icon.textContent = " ⓘ";
        icon.title = help;
        icon.setAttribute("aria-label", help);
        icon.style.cssText = "cursor:help;color:#8eb8ef;font-weight:400";
        heading.append(icon);
        row.title = help;
    }
    const video = document.createElement(mediaKind);
    video.controls = true;
    video.preload = "metadata";
    video.playsInline = true;
    video.style.cssText = `width:100%;height:${mediaKind === "audio" ? 36 : 142}px;object-fit:contain;background:#090b0e`;
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = "0";
    slider.max = "1";
    slider.step = "1";
    slider.style.width = "100%";
    const number = document.createElement("input");
    number.type = "number";
    number.min = "0";
    number.step = "1";
    number.style.cssText = "width:84px;background:#111923;color:white;border:1px solid #56606d;border-radius:4px";
    const description = document.createElement("span");
    description.style.cssText = "margin-left:8px;color:#9fb0c7";
    const controls = document.createElement("div");
    const playhead = document.createElement("button");
    playhead.textContent = "Use playhead";
    playhead.type = "button";
    playhead.style.marginLeft = "8px";
    controls.append(number, description, playhead);
    row.append(heading, video, slider, controls);
    const update = (value) => {
        const frame = Math.max(0, Math.round(Number(value) || 0));
        write(frame);
        number.value = String(frame);
        slider.value = String(Math.min(frame, Number(slider.max)));
        description.textContent = `${(frame / FPS).toFixed(2)}s · normalized 24 fps`;
        if (video.readyState && Math.abs(video.currentTime - frame / FPS) > 0.06) {
            video.currentTime = frame / FPS;
        }
    };
    slider.oninput = () => update(slider.value);
    number.onchange = () => update(number.value);
    playhead.onclick = () => update(video.currentTime * FPS);
    video.onloadedmetadata = () => {
        slider.max = String(Math.max(0, Math.ceil(video.duration * FPS) - 1));
        update(read());
    };
    return { row, video, slider, number, update, read };
}

app.registerExtension({
    name: "skeba.inpaint.source.window",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaH3InpaintSourceWindow") return;
        const original = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            original?.apply(this, arguments);
            const node = this;
            let previewVersion = 0;
            const root = document.createElement("div");
            root.style.cssText = "width:100%;box-sizing:border-box;padding:4px 8px;color:#e8edf4;font:12px sans-serif;overflow:auto";
            const intro = document.createElement("div");
            intro.textContent = "Select the source start and one fixed frame for SAM3. Use the video playhead or drag either slider.";
            intro.style.cssText = "color:#b8c5d8;line-height:1.4";
            const start = frameField("Video start frame", () => sourceControl(node, "start_frame")?.value ?? 0, (frame) => {
                const widget = sourceControl(node, "start_frame");
                if (widget) { widget.value = frame; widget.callback?.(frame); app.graph.setDirtyCanvas(true, true); }
            }, "video", "Choose where the first prompt starts in the source video. Later prompts advance automatically. Drag, type a frame number, or use the preview playhead. Positions use normalized 24 fps.");
            const reference = frameField("Fixed SAM3 reference frame", () => control(node, "reference_frame")?.value ?? 0, (frame) => {
                const widget = control(node, "reference_frame");
                if (widget) { widget.value = frame; widget.callback?.(frame); app.graph.setDirtyCanvas(true, true); }
            }, "video", "Pick a clear frame of the subject for tracking. This image stays fixed as the reference across the loop; it does not change the video start.");
            const audio = frameField("Custom audio start frame", () => control(node, "custom_audio_start_frame")?.value ?? 0, (frame) => {
                const widget = control(node, "custom_audio_start_frame");
                if (widget) { widget.value = frame; widget.callback?.(frame); app.graph.setDirtyCanvas(true, true); }
            }, "audio", "Choose where the separate audio track begins. Its position then advances with each video window. If the track runs short, the missing tail is silent.");
            const status = document.createElement("div");
            status.style.cssText = "color:#b8c5d8;margin:4px 0";
            const uploadRow = document.createElement("div");
            uploadRow.style.cssText = "display:flex;gap:8px;margin:6px 0";
            const videoSelectRow = document.createElement("div");
            videoSelectRow.style.cssText = "margin:8px 0;color:#d9e4f3";
            const videoSelectLabel = document.createElement("label");
            videoSelectLabel.textContent = "Source video ";
            const videoSelect = document.createElement("select");
            videoSelect.style.cssText = "width:100%;margin-top:4px;padding:5px;background:#111923;color:white;border:1px solid #56606d;border-radius:4px";
            videoSelect.onchange = () => {
                const widget = sourceControl(node, "video");
                if (!widget) return;
                widget.value = videoSelect.value;
                widget.callback?.(widget.value);
                previewVersion += 1;
                refresh();
                app.graph.setDirtyCanvas(true, true);
            };
            videoSelectLabel.append(videoSelect);
            videoSelectRow.append(videoSelectLabel);
            const audioSelectRow = document.createElement("div");
            audioSelectRow.style.cssText = "margin:8px 0;color:#d9e4f3";
            const audioSelectLabel = document.createElement("label");
            audioSelectLabel.textContent = "Custom audio file ";
            const audioSelect = document.createElement("select");
            audioSelect.style.cssText = videoSelect.style.cssText;
            audioSelect.onchange = () => {
                const widget = control(node, "custom_audio");
                if (!widget) return;
                widget.value = audioSelect.value;
                widget.callback?.(widget.value);
                previewVersion += 1;
                refresh();
                app.graph.setDirtyCanvas(true, true);
            };
            audioSelectLabel.append(audioSelect);
            audioSelectRow.append(audioSelectLabel);
            const makeUpload = (label, accept, widgetName) => {
                const button = document.createElement("button");
                button.textContent = label;
                button.type = "button";
                const input = document.createElement("input");
                input.type = "file";
                input.accept = accept;
                input.style.display = "none";
                button.onclick = () => input.click();
                input.onchange = async () => {
                    const file = input.files?.[0];
                    if (!file) return;
                    status.textContent = `Uploading ${file.name}…`;
                    button.disabled = true;
                    try {
                        const body = new FormData();
                        body.append("image", file, file.name);
                        body.append("type", "input");
                        const response = await api.fetchApi("/upload/image", { method: "POST", body });
                        if (!response.ok) throw new Error(await response.text());
                        const result = await response.json();
                        const widget = sourceControl(node, widgetName);
                        if (!widget) throw new Error(`Missing ${widgetName} selector`);
                        const values = widget.options?.values;
                        if (Array.isArray(values) && !values.includes(result.name)) values.push(result.name);
                        widget.value = result.name;
                        widget.callback?.(result.name);
                        previewVersion += 1;
                        if (widgetName === "custom_audio") {
                            const mode = control(node, "audio_source");
                            if (mode) { mode.value = "custom audio"; mode.callback?.(mode.value); }
                        }
                        status.textContent = `Uploaded ${result.name}`;
                        refresh();
                        app.graph.setDirtyCanvas(true, true);
                    } catch (error) {
                        status.textContent = `Upload failed: ${error.message}`;
                    } finally { button.disabled = false; input.value = ""; }
                };
                uploadRow.append(button, input);
            };
            makeUpload("Upload video", "video/*,.mkv,.mov,.m4v", "video");
            makeUpload("Upload audio", "audio/*,.wav,.mp3,.flac,.m4a,.ogg,.opus,.aac", "custom_audio");
            uploadRow.children[0].title = "Add a source video to ComfyUI's input folder and select it for this window.";
            uploadRow.children[2].title = "Add a separate audio track; this also selects Custom audio as the audio source.";
            root.append(intro, videoSelectRow, audioSelectRow, uploadRow, status, start.row, reference.row, audio.row);
            const refresh = () => {
                const videoWidget = sourceControl(node, "video");
                const filename = String(videoWidget?.value ?? "");
                const values = videoWidget?.options?.values || [];
                if (videoSelect.options.length !== values.length ||
                    values.some((value, index) => videoSelect.options[index]?.value !== value)) {
                    videoSelect.replaceChildren(...values.map((value) => new Option(value, value)));
                }
                videoSelect.value = filename;
                const hasVideo = !!filename && !filename.startsWith("(");
                if (hasVideo) {
                    const url = api.apiURL(`/view?${new URLSearchParams({ filename, type: "input", v: String(previewVersion) })}`);
                    for (const item of [start, reference]) {
                        if (item.video.src !== new URL(url, location.href).href) {
                            item.video.src = url;
                            item.video.load();
                        }
                    }
                }
                start.video.style.display = hasVideo ? "block" : "none";
                start.slider.style.display = hasVideo ? "block" : "none";
                start.update(start.read());
                const videoMode = control(node, "video_generation_mode")?.value;
                const audioDriven = videoMode === "audio drives video";
                const tracksSubject = ["source video inpaint", "inpaint only", "controlnet and inpainting"].includes(videoMode);
                reference.row.style.display = !tracksSubject || !hasVideo ? "none" : "block";
                intro.textContent = audioDriven && !hasVideo
                    ? "Audio-only source: choose custom audio or generate new audio. The audio start advances with each prompt."
                    : audioDriven
                    ? "Audio drives prompt-generated video. The source start and selected audio still advance with the loop; subject tracking is skipped."
                    : videoMode === "controlnet only"
                    ? "ControlNet guides a new video from the source frames. Subject tracking and the final inpaint composite are skipped."
                    : "Select the source start and one fixed frame for SAM3. Use the video playhead or drag either slider.";
                if (tracksSubject && hasVideo) reference.update(reference.read());
                const useCustom = control(node, "audio_source")?.value === "custom audio";
                audioSelectRow.style.display = useCustom ? "block" : "none";
                audio.row.style.display = useCustom ? "block" : "none";
                if (useCustom) {
                    const audioWidget = control(node, "custom_audio");
                    const audioName = String(audioWidget?.value ?? "");
                    const audioValues = audioWidget?.options?.values || [];
                    if (audioSelect.options.length !== audioValues.length ||
                        audioValues.some((value, index) => audioSelect.options[index]?.value !== value)) {
                        audioSelect.replaceChildren(...audioValues.map((value) => new Option(value, value)));
                    }
                    audioSelect.value = audioName;
                    if (audioName && audioName !== "(none)") {
                        const audioUrl = api.apiURL(`/view?${new URLSearchParams({ filename: audioName, type: "input", v: String(previewVersion) })}`);
                        if (audio.video.src !== new URL(audioUrl, location.href).href) {
                            audio.video.src = audioUrl;
                            audio.video.load();
                        }
                    }
                    audio.update(audio.read());
                }
            };
            const bindSourceCallbacks = () => {
                const mode = control(node, "video_generation_mode");
                if (mode) {
                    if (mode.value === "source video inpaint") mode.value = "controlnet and inpainting";
                    mode.options ||= {};
                    mode.options.values = VIDEO_MODES;
                }
                for (const widgetName of ["video", "audio_source", "custom_audio", "video_generation_mode"]) {
                    const widget = sourceControl(node, widgetName);
                    if (!widget || widget.__skebaSourceRefreshFor === node.id) continue;
                    const oldCallback = widget.callback;
                    widget.callback = function () {
                        oldCallback?.apply(this, arguments);
                        if (widgetName === "video" || widgetName === "custom_audio") previewVersion += 1;
                        refresh();
                    };
                    widget.__skebaSourceRefreshFor = node.id;
                }
            };
            bindSourceCallbacks();
            this.addDOMWidget("source_frame_picker", "custom", root,
                { serialize: false, getMinHeight: () => 515 });
            this.setSize([Math.max(this.size[0], 410), Math.max(this.size[1], 760)]);
            setTimeout(refresh, 0);
            const oldConfigure = this.onConfigure;
            this.onConfigure = function () {
                oldConfigure?.apply(this, arguments);
                setTimeout(() => { bindSourceCallbacks(); refresh(); }, 0);
            };
            const oldConnectionsChange = this.onConnectionsChange;
            this.onConnectionsChange = function () {
                oldConnectionsChange?.apply(this, arguments);
                setTimeout(() => { bindSourceCallbacks(); refresh(); }, 0);
            };
        };
    },
});
