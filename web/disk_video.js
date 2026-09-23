import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "SKEBA.DiskVideo",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaSaveClipToFile") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            this.resizable = true;
            this.addWidget("button", "Open Live Playlist", null, () => {
                const url = new URL("h3-video-playlist", window.location.href);
                if (this.properties.skeba_playlist) url.searchParams.set("project", this.properties.skeba_playlist);
                if (api.clientId) url.searchParams.set("client_id", api.clientId);
                window.open(url.href, "_blank", "noopener");
            }, { serialize: false });
            return result;
        };
        // Store by name as well as Comfy's positional widget array. Optional
        // widgets and frontend-added controls can change positional restoration.
        const serialized = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function (data) {
            const result = serialized?.apply(this, arguments);
            const toggles = {};
            for (const name of ["preview_clip"]) {
                const widget = this.widgets?.find(item => item.name === name);
                if (typeof widget?.value === "boolean") toggles[name] = widget.value;
            }
            data.properties ||= {};
            data.properties.skeba_clip_toggles = toggles;
            return result;
        };
        const configured = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (data) {
            const result = configured?.apply(this, arguments);
            const toggles = data.properties?.skeba_clip_toggles;
            for (const name of ["preview_clip"]) {
                const widget = this.widgets?.find(item => item.name === name);
                if (widget && typeof toggles?.[name] === "boolean") widget.value = toggles[name];
            }
            return result;
        };
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            executed?.apply(this, arguments);
            if (message.skeba_playlist?.[0]) this.properties.skeba_playlist = message.skeba_playlist[0];
            const clip = message.skeba_clip_preview?.[0];
            if (!clip) {
                if (this.skebaClipVideo) {
                    this.skebaClipVideo.pause();
                    this.skebaClipVideo.removeAttribute("src");
                    this.skebaClipVideo.load();
                    this.skebaClipVideo.style.display = "none";
                    if (this.size) this.setSize?.([this.size[0], this.computeSize()[1]]);
                    this.setDirtyCanvas?.(true, true);
                }
                return;
            }
            if (!this.skebaClipVideo) {
                const video = document.createElement("video");
                video.controls = true;
                video.playsInline = true;
                video.preload = "metadata";
                video.style.cssText = "width:100%;height:100%;object-fit:contain;background:#111;";
                const height = (width = this.size?.[0] || 320) => {
                    if (video.style.display === "none") return 0;
                    const ratio = video.videoWidth && video.videoHeight ? video.videoWidth / video.videoHeight : 16 / 9;
                    return Math.max(1, Math.round((width - 20) / ratio));
                };
                const widget = this.addDOMWidget("skeba_clip_preview", "video", video, {
                    serialize: false,
                    getHeight: () => height(),
                    getMinHeight: () => height(),
                    getMaxHeight: () => height(),
                });
                // Legacy canvas and current DOM layout use different sizing hooks.
                widget.computeSize = width => [width, height(width)];
                video.onloadedmetadata = () => {
                    if (this.size) this.setSize?.([this.size[0], this.computeSize()[1]]);
                    this.setDirtyCanvas?.(true, true);
                };
                this.skebaClipVideo = video;
            }
            const video = this.skebaClipVideo;
            video.pause();
            video.src = api.apiURL(`/view?${new URLSearchParams(clip)}`);
            video.style.display = "block";
            video.load();
            if (this.size) this.setSize?.([this.size[0], this.computeSize()[1]]);
            this.setDirtyCanvas?.(true, true);
        };
        const removed = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function (...args) {
            if (this.skebaClipVideo) {
                this.skebaClipVideo.pause();
                this.skebaClipVideo.removeAttribute("src");
                this.skebaClipVideo.load();
            }
            return removed?.apply(this, args);
        };
    },
});
