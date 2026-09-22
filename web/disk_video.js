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
        };
    },
});
