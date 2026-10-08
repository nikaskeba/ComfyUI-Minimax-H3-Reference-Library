import {createTemplatePreview} from "./compiler_template_preview.js";
import {app} from "../../scripts/app.js";

app.registerExtension({
    name: "Skeba.CompilerTemplates",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaH3CompilerTemplates") return;
        const fields = Object.entries(nodeData.input.required).map(([name, [, options]]) => ({
            name, default: options.default, group: options.tooltip.split(" | ")[0], guide: options.tooltip.split(" | ")[1],
        }));
        const fieldNames = new Set(fields.map(field => field.name));
        const allowedPlaceholders = new Set(fields[0].guide.split("Placeholders: ")[1].split(". Unavailable")[0].split(", "));
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            const widgets = new Map(this.widgets.map(widget => [widget.name, widget]));
            for (const field of fields) {
                const widget = widgets.get(field.name);
                widget.type = "converted-widget";
                widget.computeSize = () => [0, -4];
                if (widget.inputEl) widget.inputEl.hidden = true;
            }
            const root = document.createElement("div");
            root.style.cssText = "height:100%;overflow:auto;padding:10px;box-sizing:border-box;background:var(--comfy-menu-bg,#222);color:var(--input-text,#eee);font:13px system-ui";
            const tabs = document.createElement("select");
            tabs.setAttribute("aria-label", "Template group");
            for (const group of new Set(fields.map(field => field.group))) tabs.add(new Option(group, group));
            tabs.style.width = "100%";
            const reset = document.createElement("button");
            reset.textContent = "Reset to defaults"; reset.type = "button";
            const importButton = document.createElement("button");
            importButton.textContent = "Import template JSON"; importButton.type = "button";
            const importPanel = document.createElement("div");
            importPanel.hidden = true;
            importPanel.style.cssText = "margin:8px 0;padding:10px;border:1px solid #52616a;border-radius:5px";
            const importHint = document.createElement("p");
            importHint.textContent = "Paste JSON with a templates object, or choose a .json file. Only named fields are updated; other fields keep their current text. Review before applying.";
            const importFile = document.createElement("input");
            importFile.type = "file"; importFile.accept = ".json,application/json";
            importFile.setAttribute("aria-label", "Choose template JSON file");
            const importText = document.createElement("textarea");
            importText.rows = 7; importText.spellcheck = false;
            importText.setAttribute("aria-label", "Template JSON to import");
            importText.style.cssText = "display:block;width:100%;box-sizing:border-box;margin:6px 0;resize:vertical";
            importText.placeholder = '{"templates":{"voice_reference":"[[audio]] is the voice for [[identity]]."}}';
            const importError = document.createElement("div");
            importError.setAttribute("role", "alert"); importError.style.color = "#ff9292";
            const applyImport = document.createElement("button");
            applyImport.textContent = "Apply imported templates"; applyImport.type = "button";
            const cancelImport = document.createElement("button");
            cancelImport.textContent = "Cancel import"; cancelImport.type = "button";
            importPanel.append(importHint, importFile, importText, importError, applyImport, cancelImport);
            importButton.onclick = () => { importPanel.hidden = false; importError.textContent = ""; importText.focus(); };
            cancelImport.onclick = () => { importPanel.hidden = true; importError.textContent = ""; };
            importFile.onchange = async () => {
                const file = importFile.files?.[0];
                if (!file) return;
                try { importText.value = await file.text(); importError.textContent = ""; }
                catch (error) { importError.textContent = `Could not read ${file.name}: ${error.message}`; }
            };
            applyImport.onclick = () => {
                try {
                    const data = JSON.parse(importText.value);
                    if (!data || Array.isArray(data) || typeof data !== "object" ||
                        Object.keys(data).some(key => !["version", "templates"].includes(key)) ||
                        (data.version !== undefined && data.version !== 1) ||
                        !data.templates || Array.isArray(data.templates) || typeof data.templates !== "object") {
                        throw new Error("Expected a templates object and optional version: 1.");
                    }
                    const entries = Object.entries(data.templates);
                    if (!entries.length) throw new Error("No template fields were provided.");
                    for (const [name, value] of entries) {
                        if (!fieldNames.has(name)) throw new Error(`Unknown template field: ${name}.`);
                        if (typeof value !== "string") throw new Error(`${name} must contain text.`);
                        const tokens = [...value.matchAll(/\[\[([a-z_]+)\]\]/g)];
                        const remainder = value.replace(/\[\[([a-z_]+)\]\]/g, "");
                        if (tokens.some(match => !allowedPlaceholders.has(match[1])) || remainder.includes("[[") || remainder.includes("]]")) {
                            throw new Error(`${name} contains an invalid placeholder.`);
                        }
                    }
                    for (const [name, value] of entries) {
                        const widget = widgets.get(name);
                        widget.value = value;
                        widget.callback?.(value);
                    }
                    tabs.value = fields.find(field => field.name === entries[0][0]).group;
                    render(); dirty(); preview.update();
                    importPanel.hidden = true;
                    importError.textContent = "";
                } catch (error) {
                    importError.textContent = error instanceof SyntaxError ? `Invalid JSON: ${error.message}` : error.message;
                }
            };
            const guide = document.createElement("p");
            guide.textContent = "All fields accept the shared [[placeholder]] tokens. They use the current reference; unavailable values are empty. Global fields have no individual character. [[identity]] combines [[subject]] and [[speaker]]; [[speaker_id]] gives S1 without parentheses. Spaces and punctuation are literal. Empty fields suppress that phrase. Connect to compiler_templates on both compiler and validator.";
            const content = document.createElement("div");
            const dirty = () => this.graph?.setDirtyCanvas(true, true);
            let examples = {};
            const previewFields = new Map();
            const showExamples = value => {
                examples = value;
                for (const [name, box] of previewFields) box.textContent = examples[name]?.length
                    ? [...new Set(examples[name])].map(text => text || "(Phrase suppressed)").join("\n")
                    : "Not used in this example. Choose a reference/usage that applies; global binding needs multiple speakers.";
            };
            const preview = createTemplatePreview(this, () => JSON.stringify({version:1, templates:Object.fromEntries(fields.map(field => [field.name, widgets.get(field.name).value]))}), showExamples);
            const render = () => {
                previewFields.clear();
                content.replaceChildren();
                for (const field of fields.filter(field => field.group === tabs.value)) {
                    const label = document.createElement("label");
                    label.style.cssText = "display:block;margin:12px 0";
                    const title = document.createElement("strong"); title.textContent = field.name.replaceAll("_", " ");
                    const help = document.createElement("div"); help.textContent = field.guide;
                    const input = document.createElement("textarea"); input.rows = 4; input.spellcheck = false;
                    input.setAttribute("aria-label", field.name);
                    input.style.cssText = "width:100%;box-sizing:border-box;resize:vertical";
                    input.value = widgets.get(field.name).value;
                    input.oninput = () => {
                        const widget = widgets.get(field.name);
                        widget.value = input.value;
                        widget.callback?.(input.value);
                        dirty(); preview.update();
                    };
                    label.append(title, help, input); content.append(label);
                    const example = document.createElement("pre"); example.setAttribute("aria-label", field.name + " preview");
                    example.style.cssText = "white-space:pre-wrap;overflow-wrap:anywhere;padding:8px;border-left:3px solid #5c9;font:12px monospace";
                    previewFields.set(field.name, example); content.append(example);
                }
            };
            const renderFields = render;
            tabs.onchange = () => {renderFields(); showExamples(examples);};
            reset.onclick = () => {
                for (const field of fields) {
                    const widget = widgets.get(field.name); widget.value = field.default;
                    widget.callback?.(widget.value);
                }
                render(); dirty(); preview.update();
            };
            for (const event of ["pointerdown", "keydown", "wheel"]) root.addEventListener(event, e => e.stopPropagation());
            root.append(tabs, reset, importButton, importPanel, guide, preview.element, content);
            this.addDOMWidget("template_editor", "custom", root, {serialize: false, getMinHeight: () => 300});
            this.skebaTemplatesRefresh = () => {render(); preview.restore();};
            const removed = this.onRemoved;
            this.onRemoved = function (...args) {preview.dispose(); return removed?.apply(this, args);};
            this.setSize([560, 650]); this.resizable = true;
            render(); showExamples({}); return result;
        };
        const configure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configure?.apply(this, args);
            this.skebaTemplatesRefresh?.(); return result;
        };
    },
});
