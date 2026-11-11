import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const defaults = [
    {name: "Image Upscale", description: "Upscales the source image while preserving its content.", text: "Upscale [[source]] with fine detail and clean edges. Preserve the composition, identity, and colors."},
    {name: "Style Enhancer", description: "Apply the second image's style to the first image.", text: "Take [[source]] and change its style to match [[style]]. Preserve the source subject and composition."},
];
const element = (tag, text) => {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    return e;
};

app.registerExtension({
    name: "Skeba.ImagePromptBuilder",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "H3ImagePromptBuilder") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            const node = this;
            const widget = node.widgets.find(w => w.name === "prompt");
            widget.type = "converted-widget";
            widget.computeSize = () => [0, -4];
            if (widget.inputEl) widget.inputEl.style.display = "none";
            const panel = element("div");
            panel.style.cssText = "padding:10px;box-sizing:border-box;width:100%;height:100%;overflow:auto;background:var(--comfy-menu-bg,#222);color:var(--input-text,#ddd);font:13px sans-serif;display:flex;flex-direction:column;gap:8px";
            const message = element("div", "Connect prompt output to H3 Image Tagged Reference Prompt → prompt.");
            const editor = element("textarea");
            editor.placeholder = "Write a prompt, or insert references and apply a template below.";
            editor.style.cssText = "width:100%;min-height:150px;box-sizing:border-box;resize:vertical";
            editor.value = widget.value || "";
            const changed = () => { widget.value = editor.value; app.graph?.setDirtyCanvas(true, true); };
            editor.oninput = changed;
            const insert = text => {
                editor.setRangeText(text, editor.selectionStart, editor.selectionEnd, "end");
                changed(); editor.focus();
            };
            const status = element("div");
            const button = (label, action) => {
                const b = element("button", label); b.type = "button";
                b.onclick = async () => { try { await action(); } catch (e) { status.textContent = e.message; } };
                return b;
            };
            let choices = {references: [], photos: []};
            const search = element("input"); search.placeholder = "Search references by name or description";
            const kind = element("select");
            for (const value of ["all", "character", "location", "object", "clothing"]) {
                const option = element("option", value); option.value = value; kind.append(option);
            }
            const matches = element("select"); matches.size = 4;
            const filter = () => {
                matches.replaceChildren();
                for (const r of choices.references) {
                    if (kind.value !== "all" && r.kind !== kind.value) continue;
                    if (!`${r.name} ${r.tag} ${r.description}`.toLowerCase().includes(search.value.toLowerCase())) continue;
                    const option = element("option", `${r.name} (${r.kind})`);
                    option.value = r.tag; option.title = r.description; matches.append(option);
                }
            };
            search.oninput = filter; kind.onchange = filter;
            const addReference = () => { if (matches.value) insert(`{${matches.value}}`); };
            matches.ondblclick = addReference;
            const photo = element("select");
            const preview = element("img");
            preview.style.cssText = "max-width:100%;height:90px;object-fit:contain;display:none";
            const showPhoto = () => {
                if (!photo.value) { preview.style.display = "none"; return; }
                const parts = photo.value.split("/");
                preview.src = api.apiURL(`/view?${new URLSearchParams({filename: parts.pop(), subfolder: parts.join("/"), type: "input"})}`);
                preview.style.display = "block";
            };
            photo.onchange = showPhoto;
            const reload = async () => {
                const response = await api.fetchApi("/api/h3-image-prompt/choices");
                if (!response.ok) throw new Error("Could not load references. Restart ComfyUI after installing this node.");
                choices = await response.json(); filter();
                const selected = photo.value; photo.replaceChildren(element("option", "Choose a one-time photo"));
                photo.firstChild.value = "";
                for (const name of choices.photos) { const option = element("option", name); option.value = name; photo.append(option); }
                photo.value = selected; showPhoto();
            };
            const addPhoto = () => { if (photo.value) insert(`{photo:${photo.value}}`); };
            const upload = button("Upload one-time photo…", () => {
                const picker = element("input"); picker.type = "file"; picker.accept = ".png,.jpg,.jpeg,.webp,.bmp,.tiff";
                picker.onchange = async () => {
                    const file = picker.files?.[0]; if (!file) return;
                    upload.disabled = true;
                    try {
                        const body = new FormData(); body.append("image", file); body.append("type", "input"); body.append("subfolder", "Skeba One-Time Photos");
                        const response = await api.fetchApi("/upload/image", {method: "POST", body});
                        if (!response.ok) throw new Error(`Upload failed: HTTP ${response.status}`);
                        const saved = await response.json(); await reload();
                        photo.value = [saved.subfolder, saved.name].filter(Boolean).join("/"); showPhoto(); addPhoto();
                        status.textContent = "Photo inserted. Stored in input; not added to your reference library.";
                    } catch (e) { status.textContent = e.message; }
                    finally { upload.disabled = false; }
                };
                picker.click();
            });
            const template = element("select");
            const description = element("div");
            const variables = element("div"); variables.style.cssText = "display:flex;flex-direction:column;gap:5px";
            const templates = () => node.properties.imagePromptTemplates ??= structuredClone(defaults);
            let fields = [];
            const selectTemplate = () => {
                const t = templates()[Number(template.value)];
                description.textContent = t?.description || "";
                variables.replaceChildren(); fields = [];
                if (!t) return;
                for (const name of new Set([...t.text.matchAll(/\[\[([^\]]+)\]\]/g)].map(m => m[1]))) {
                    const row = element("label", `${name}: `);
                    const input = element("input"); input.placeholder = "Reference tag, photo tag, or replacement text";
                    row.append(input, button("Use selected reference", () => { if (matches.value) input.value = `{${matches.value}}`; }),
                        button("Use selected photo", () => { if (photo.value) input.value = `{photo:${photo.value}}`; }));
                    variables.append(row); fields.push({name, input});
                }
            };
            const refreshTemplates = () => {
                template.replaceChildren();
                templates().forEach((t, i) => { const o = element("option", t.name); o.value = i; template.append(o); });
                selectTemplate();
            };
            template.onchange = selectTemplate;
            const apply = button("Replace prompt with template", () => {
                const t = templates()[Number(template.value)]; if (!t) return;
                const values = Object.fromEntries(fields.map(f => [f.name, f.input.value]));
                if (fields.some(f => !f.input.value.trim())) { status.textContent = "Fill in the template replacements first."; return; }
                editor.value = t.text.replace(/\[\[([^\]]+)\]\]/g, (_, name) => values[name]); changed();
                status.textContent = "Template applied. You can edit the prompt above before running.";
            });
            const custom = element("details"); custom.append(element("summary", "Add / edit templates"));
            const title = element("input"); title.placeholder = "Template name";
            const summary = element("input"); summary.placeholder = "Short description";
            const body = element("textarea"); body.placeholder = "Template text, e.g. Upscale [[source]] with [[detail]].";
            for (const e of [title, summary, body]) { e.style.cssText = "display:block;width:100%;box-sizing:border-box;margin:5px 0"; custom.append(e); }
            custom.append(button("Load selected template for editing", () => {
                const t = templates()[Number(template.value)]; if (t) { title.value = t.name; summary.value = t.description; body.value = t.text; }
            }), button("Save template", () => {
                if (!title.value.trim() || !body.value.trim()) { status.textContent = "Enter a template name and text."; return; }
                const t = {name: title.value.trim(), description: summary.value, text: body.value};
                const list = templates(); const index = list.findIndex(x => x.name === t.name);
                if (index < 0) list.push(t); else list[index] = t;
                refreshTemplates(); template.value = list.indexOf(t); selectTemplate();
                app.graph?.setDirtyCanvas(true, true); status.textContent = "Template saved in this node. Save the workflow to keep it.";
            }), button("Delete selected template", () => { templates().splice(Number(template.value), 1); refreshTemplates(); app.graph?.setDirtyCanvas(true, true); }));
            panel.append(message, editor, element("strong", "References"), search, kind, matches, button("Insert selected reference", addReference),
                element("strong", "One-time photos"), photo, preview, button("Insert selected photo", addPhoto), upload,
                button("Refresh references / photos", reload), element("strong", "Templates"), template, description, variables, apply, custom, status);
            for (const event of ["pointerdown", "wheel", "keydown"]) panel.addEventListener(event, e => e.stopPropagation());
            node.addDOMWidget("image_prompt_builder", "custom", panel, {serialize: false, getMinHeight: () => 700});
            const configure = node.onConfigure;
            node.onConfigure = (...values) => { configure?.apply(node, values); editor.value = widget.value || ""; refreshTemplates(); };
            node.setSize([650, 800]); refreshTemplates(); reload().catch(e => { status.textContent = e.message; });
            return result;
        };
    },
});
