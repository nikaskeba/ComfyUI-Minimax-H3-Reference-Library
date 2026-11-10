import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "Skeba.AVMixingSource",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (["SkebaH3VideoEditMask", "SkebaH3AudioEditMask"].includes(nodeData.name)) {
            const configure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function (...args) {
                configure?.apply(this, args);
                if (!this.properties?.skeba_ranges_only) return;
                for (const widget of this.widgets || []) {
                    if (["edit_start_seconds", "edit_end_seconds", "extend_to_last_frame"].includes(widget.name)) {
                        widget.type = "converted-widget";
                        widget.computeSize = () => [0, -4];
                    }
                }
                this.setSize(this.computeSize());
            };
            return;
        }
        if (nodeData.name !== "SkebaH3MixingSource") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            const video = document.createElement("video");
            video.controls = true;
            video.preload = "auto";
            video.style.cssText = "width:100%;height:220px;object-fit:contain;background:#111";
            const find = name => this.widgets?.find(w => w.name === name);
            const panel = document.createElement("div");
            panel.style.cssText = "width:100%;color:var(--input-text);padding:4px;box-sizing:border-box";
            const label = document.createElement("div");
            const timeline = document.createElement("input");
            timeline.type = "range";
            timeline.min = 0;
            timeline.max = 0;
            timeline.step = 1 / 24;
            timeline.style.width = "100%";
            timeline.title = "Drag to set the source start immediately";
            const time = seconds => {
                const frames = Math.round(seconds * 24);
                return `${Math.floor(frames / 1440)}:${String(Math.floor(frames / 24) % 60).padStart(2, "0")}.${String(Math.round(frames % 24 * 1000 / 24)).padStart(3, "0")}`;
            };
            const showStart = () => {
                const start = Number(find("start_seconds")?.value || 0);
                timeline.value = start;
                label.textContent = `Start: ${time(start)} (${start.toFixed(3)} s) / ${time(Number.isFinite(video.duration) ? video.duration : 0)}`;
            };
            const setStart = seconds => {
                const limit = Number.isFinite(video.duration) ? Math.max(0, video.duration - 1 / 24) : seconds;
                const widget = find("start_seconds");
                widget.value = Math.max(0, Math.min(Math.round(seconds * 24), Math.floor(limit * 24))) / 24;
                widget.callback?.(widget.value);
                video.pause();
                video.currentTime = widget.value;
                showStart();
                app.graph?.setDirtyCanvas(true, true);
            };
            const startWidget = find("start_seconds");
            if (startWidget) {
                const callback = startWidget.callback;
                startWidget.callback = (...values) => {
                    callback?.apply(this, values);
                    video.currentTime = Number(startWidget.value);
                    showStart();
                };
            }
            timeline.oninput = () => setStart(Number(timeline.value));
            // Native video scrubbing also updates the selected start, without seeking again.
            video.onseeking = () => {
                if (!video.paused) return;
                find("start_seconds").value = Math.round(video.currentTime * 24) / 24;
                showStart();
                app.graph?.setDirtyCanvas(true, true);
            };
            video.onseeked = () => app.graph?.setDirtyCanvas(true, true);
            const buttons = document.createElement("div");
            buttons.style.cssText = "display:flex;gap:4px;flex-wrap:wrap";
            for (const [text, delta] of [["-1s", -1], ["-1 frame", -1 / 24], ["+1 frame", 1 / 24], ["+1s", 1]]) {
                const button = document.createElement("button");
                button.textContent = text;
                button.type = "button";
                button.onclick = () => setStart(Number(find("start_seconds").value) + delta);
                buttons.append(button);
            }
            const usePlayhead = document.createElement("button");
            usePlayhead.textContent = "Use playhead as start";
            usePlayhead.onclick = () => setStart(video.currentTime);
            buttons.append(usePlayhead);
            panel.append(video, label, timeline, buttons);
            for (const event of ["pointerdown", "wheel", "keydown"]) panel.addEventListener(event, e => e.stopPropagation());
            video.onloadedmetadata = () => {
                timeline.max = Math.max(0, video.duration - 1 / 24);
                video.currentTime = Number(find("start_seconds")?.value || 0);
                showStart();
            };
            const refresh = () => {
                const name = find("video")?.value;
                if (!name || name === "Upload a video") return;
                const parts = name.split("/");
                video.src = api.apiURL(`/view?${new URLSearchParams({filename: parts.pop(), subfolder: parts.join("/"), type: "input"})}`);
                showStart();
            };
            const selection = find("video");
            if (selection) {
                const callback = selection.callback;
                selection.callback = (...values) => { callback?.apply(this, values); refresh(); };
            }
            const audioPanel = document.createElement("div");
            const audio = document.createElement("audio");
            audio.controls = true;
            audio.preload = "metadata";
            audio.style.width = "100%";
            const audioLabel = document.createElement("div");
            const audioSlider = document.createElement("input");
            audioSlider.type = "range";
            audioSlider.min = 0;
            audioSlider.max = 0;
            audioSlider.step = 1 / 24;
            audioSlider.style.width = "100%";
            audioSlider.title = "Custom audio start (independent of video start)";
            const showAudioStart = () => {
                const start = Number(find("custom_audio_start_seconds")?.value || 0);
                audioSlider.value = start;
                audioLabel.textContent = `Audio start: ${time(start)} (${start.toFixed(3)} s)`;
            };
            const setAudioStart = seconds => {
                const limit = Number.isFinite(audio.duration) ? Math.max(0, audio.duration - 1 / 24) : seconds;
                const widget = find("custom_audio_start_seconds");
                widget.value = Math.max(0, Math.min(Math.round(seconds * 24), Math.floor(limit * 24))) / 24;
                audio.pause();
                audio.currentTime = widget.value;
                showAudioStart();
                app.graph?.setDirtyCanvas(true, true);
            };
            audioSlider.oninput = () => setAudioStart(Number(audioSlider.value));
            audio.onseeking = () => {
                if (!audio.paused) return;
                find("custom_audio_start_seconds").value = Math.round(audio.currentTime * 24) / 24;
                showAudioStart();
                app.graph?.setDirtyCanvas(true, true);
            };
            audio.onloadedmetadata = () => {
                audioSlider.max = Math.max(0, audio.duration - 1 / 24);
                audio.currentTime = Number(find("custom_audio_start_seconds")?.value || 0);
                showAudioStart();
            };
            const audioButtons = document.createElement("div");
            for (const [text, delta] of [["-1s", -1], ["+1s", 1]]) {
                const button = document.createElement("button");
                button.textContent = text;
                button.onclick = () => setAudioStart(Number(find("custom_audio_start_seconds").value) + delta);
                audioButtons.append(button);
            }
            const audioPlayhead = document.createElement("button");
            audioPlayhead.textContent = "Use audio playhead as start";
            audioPlayhead.onclick = () => setAudioStart(audio.currentTime);
            audioButtons.append(audioPlayhead);
            audioPanel.append(audioLabel, audio, audioSlider, audioButtons);
            panel.append(audioPanel);
            const refreshAudio = () => {
                const active = find("audio_source")?.value === "custom audio";
                audioPanel.style.display = active ? "block" : "none";
                if (!active) audio.pause();
                const name = find("custom_audio")?.value;
                if (name && name !== "(none)") {
                    const parts = name.split("/");
                    const url = api.apiURL(`/view?${new URLSearchParams({filename: parts.pop(), subfolder: parts.join("/"), type: "input"})}`);
                    if (audio.getAttribute("src") !== url) audio.src = url;
                } else { audio.pause(); audio.removeAttribute("src"); }
                showAudioStart();
            };
            for (const name of ["audio_source", "custom_audio", "custom_audio_start_seconds"]) {
                const widget = find(name);
                const callback = widget?.callback;
                if (widget) widget.callback = (...values) => {
                    callback?.apply(this, values);
                    if (name === "custom_audio_start_seconds") setAudioStart(Number(widget.value));
                    refreshAudio();
                };
            }
            this.addDOMWidget("source_preview", "video", panel, {serialize: false, getMinHeight: () => find("audio_source")?.value === "custom audio" ? 460 : 315});
            const configured = this.onConfigure;
            this.onConfigure = (...values) => { configured?.apply(this, values); refresh(); refreshAudio(); };
            const removed = this.onRemoved;
            this.onRemoved = (...values) => { video.pause(); video.removeAttribute("src"); video.load(); audio.pause(); audio.removeAttribute("src"); audio.load(); removed?.apply(this, values); };
            refresh();
            refreshAudio();
            return result;
        };
    },
});
