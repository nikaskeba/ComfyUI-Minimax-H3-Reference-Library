import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "Skeba.MIDILoaderUpload",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaLoadMIDI") return;

        const originalCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = originalCreated?.apply(this, args);
            const node = this;
            node.addWidget("button", "Upload MIDI…", null, async () => {
                const picker = document.createElement("input");
                picker.type = "file";
                picker.accept = ".mid,.midi,audio/midi,audio/x-midi";
                picker.onchange = async () => {
                    const file = picker.files?.[0];
                    if (!file) return;
                    if (!/\.(mid|midi)$/i.test(file.name)) {
                        alert("Choose a .mid or .midi file.");
                        return;
                    }
                    const button = node.widgets?.find(widget => widget.name === "Upload MIDI…");
                    if (button) button.name = "Uploading MIDI…";
                    try {
                        const body = new FormData();
                        body.append("image", file);
                        body.append("type", "input");
                        body.append("subfolder", "Skeba Music/MIDI");
                        const response = await api.fetchApi("/upload/image", { method: "POST", body });
                        if (!response.ok) throw new Error(`Upload failed (HTTP ${response.status})`);
                        const uploaded = await response.json();
                        const selection = `input/${uploaded.subfolder}/${uploaded.name}`;
                        const widget = node.widgets?.find(item => item.name === "file");
                        if (!widget) throw new Error("The loader's file selector was not found.");
                        const values = widget.options?.values;
                        if (Array.isArray(values)) {
                            const placeholder = values.indexOf("No MIDI files found");
                            if (placeholder >= 0) values.splice(placeholder, 1);
                            if (!values.includes(selection)) values.push(selection);
                        }
                        widget.value = selection;
                        widget.callback?.(selection, node, widget);
                        app.graph?.setDirtyCanvas(true, true);
                    } catch (error) {
                        console.error("[Skeba Load MIDI]", error);
                        alert(`Could not upload MIDI: ${error.message}`);
                    } finally {
                        if (button) button.name = "Upload MIDI…";
                    }
                };
                picker.click();
            });
            return result;
        };
    },
});
