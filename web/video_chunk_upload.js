import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "Skeba.VideoChunkUpload",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaVideoChunkPlan") return;

        const originalCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = originalCreated?.apply(this, args);
            const node = this;
            let uploading = false;
            const button = node.addWidget("button", "Upload video…", null, () => {
                if (uploading) return;
                const picker = document.createElement("input");
                picker.type = "file";
                picker.accept = ".mp4,.mkv,.mov,.webm,.avi,.m4v";
                picker.onchange = async () => {
                    const file = picker.files?.[0];
                    if (!file) return;
                    if (!/\.(mp4|mkv|mov|webm|avi|m4v)$/i.test(file.name)) {
                        alert("Choose an MP4, MKV, MOV, WebM, AVI, or M4V video.");
                        return;
                    }
                    uploading = true;
                    button.name = "Uploading video…";
                    app.graph?.setDirtyCanvas(true, true);
                    try {
                        const body = new FormData();
                        body.append("image", file, file.name);
                        body.append("type", "input");
                        body.append("subfolder", "Skeba Video");
                        const response = await api.fetchApi("/upload/image", { method: "POST", body });
                        if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                        const uploaded = await response.json();
                        const selection = [uploaded.subfolder, uploaded.name].filter(Boolean).join("/");
                        const widget = node.widgets.find(item => item.name === "video");
                        const values = widget.options.values;
                        const placeholder = values.indexOf("Place a video in ComfyUI/input");
                        if (placeholder >= 0) values.splice(placeholder, 1);
                        if (!values.includes(selection)) values.push(selection);
                        values.sort();
                        widget.value = selection;
                        widget.callback?.(selection, node, widget);
                    } catch (error) {
                        alert(`Could not upload video: ${error.message}`);
                    } finally {
                        uploading = false;
                        button.name = "Upload video…";
                        app.graph?.setDirtyCanvas(true, true);
                    }
                };
                picker.click();
            }, { serialize: false });
            return result;
        };
    },
});
