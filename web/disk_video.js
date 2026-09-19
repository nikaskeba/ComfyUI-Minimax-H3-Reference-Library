import { app } from "../../scripts/app.js";

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
                window.open(url.href, "_blank", "noopener");
            }, { serialize: false });
            return result;
        };
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            executed?.apply(this, arguments);
            if (message.skeba_playlist?.[0]) this.properties.skeba_playlist = message.skeba_playlist[0];
        };
    },
});
