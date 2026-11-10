import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "Skeba.VideoChunkUpload",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (!["SkebaVideoChunkPlan", "SkebaH3MixingSource"].includes(nodeData.name)) return;

        const originalCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = originalCreated?.apply(this, args);
            const node = this;
            const uploads = [{name: "video", label: "video", folder: "Skeba Video", extensions: ["mp4", "mkv", "mov", "webm", "avi", "m4v"]}];
            if (nodeData.name === "SkebaH3MixingSource") uploads.push({name: "custom_audio", label: "custom audio", folder: "Skeba Audio", extensions: ["wav", "mp3", "flac", "m4a", "ogg", "opus", "aac", "mp4", "mkv"]});
            for (const upload of uploads) {
                let uploading = false;
                const button = node.addWidget("button", `Upload ${upload.label}…`, null, () => {
                    if (uploading) return;
                    const picker = document.createElement("input");
                    picker.type = "file";
                    picker.accept = upload.extensions.map(ext => `.${ext}`).join(",");
                    picker.onchange = async () => {
                        const file = picker.files?.[0];
                        if (!file) return;
                        if (!upload.extensions.includes(file.name.split(".").pop().toLowerCase())) {
                            alert(`Choose a supported ${upload.label} file: ${picker.accept}`);
                            return;
                        }
                        uploading = true;
                        button.name = `Uploading ${upload.label}…`;
                        app.graph?.setDirtyCanvas(true, true);
                        try {
                            const body = new FormData();
                            body.append("image", file, file.name);
                            body.append("type", "input");
                            body.append("subfolder", upload.folder);
                            const response = await api.fetchApi("/upload/image", { method: "POST", body });
                            if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                            const uploaded = await response.json();
                            const selection = [uploaded.subfolder, uploaded.name].filter(Boolean).join("/");
                            const widget = node.widgets.find(item => item.name === upload.name);
                            const values = widget.options.values;
                            const placeholder = values.findIndex(value => ["Place a video in ComfyUI/input", "Upload a video"].includes(value));
                            if (placeholder >= 0) values.splice(placeholder, 1);
                            if (!values.includes(selection)) values.push(selection);
                            values.sort();
                            widget.value = selection;
                            widget.callback?.(selection, node, widget);
                            if (upload.name === "custom_audio") {
                                const source = node.widgets.find(item => item.name === "audio_source");
                                source.value = "custom audio";
                                source.callback?.(source.value);
                            }
                        } catch (error) {
                            alert(`Could not upload ${upload.label}: ${error.message}`);
                        } finally {
                            uploading = false;
                            button.name = `Upload ${upload.label}…`;
                            app.graph?.setDirtyCanvas(true, true);
                        }
                    };
                    picker.click();
                }, { serialize: false });
            }
            return result;
        };
    },
});
