import { app } from "../../scripts/app.js";

export function parseChoices(text) {
    return [...new Set(String(text).split(/[\r\n,]+/).map(value => value.trim()).filter(Boolean))];
}

app.registerExtension({
    name: "Skeba.CustomChoice",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaCustomChoice") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            const choices = this.widgets.find(widget => widget.name === "choices");
            const selected = this.widgets.find(widget => widget.name === "selected");
            for (const widget of [choices, selected]) {
                widget.type = "converted-widget";
                widget.computeSize = () => [0, -4];
                if (widget.inputEl) widget.inputEl.hidden = true;
            }
            const root = document.createElement("div");
            root.style.cssText = "padding:8px;box-sizing:border-box;display:grid;gap:8px;color:var(--input-text,#eee);font:13px system-ui;background:var(--comfy-menu-bg,#222);height:100%;overflow:auto";
            const select = document.createElement("select");
            select.setAttribute("aria-label", "Selected choice");
            const edit = document.createElement("button"); edit.textContent = "Edit choices";
            const panel = document.createElement("div"); panel.hidden = true;
            const hint = document.createElement("p"); hint.textContent = "One choice per line (or comma-separated). Values must match the target node exactly.";
            const input = document.createElement("textarea"); input.rows = 5; input.setAttribute("aria-label", "Custom choices");
            input.style.cssText = "width:100%;box-sizing:border-box;resize:vertical";
            const error = document.createElement("div"); error.setAttribute("role", "alert"); error.style.color = "#ff9292";
            const apply = document.createElement("button"); apply.textContent = "Apply choices";
            const cancel = document.createElement("button"); cancel.textContent = "Cancel";
            const dirty = () => this.graph?.setDirtyCanvas(true, true);
            const refresh = () => {
                const values = parseChoices(choices.value);
                select.replaceChildren(...values.map(value => new Option(value, value)));
                // Do not silently change a saved selection during workflow restoration.
                if (!values.includes(selected.value)) select.add(new Option(`Unavailable: ${selected.value}`, selected.value));
                select.value = selected.value;
            };
            select.onchange = () => { selected.value = select.value; dirty(); };
            edit.onclick = () => { input.value = choices.value; panel.hidden = false; edit.hidden = true; error.textContent = ""; input.focus(); };
            const close = () => { panel.hidden = true; edit.hidden = false; dirty(); };
            apply.onclick = () => {
                const values = parseChoices(input.value);
                if (!values.length) { error.textContent = "Add at least one choice."; return; }
                choices.value = values.join("\n");
                if (!values.includes(selected.value)) selected.value = values[0];
                refresh(); close();
            };
            cancel.onclick = close;
            for (const event of ["pointerdown", "keydown", "wheel"]) root.addEventListener(event, e => e.stopPropagation());
            panel.append(hint, input, error, apply, cancel); root.append(select, edit, panel);
            this.addDOMWidget("choice_editor", "custom", root, {serialize: false, getMinHeight: () => 70});
            this.skebaChoiceRefresh = () => { close(); refresh(); };
            this.setSize([330, 190]); this.resizable = true;
            refresh();
            return result;
        };
        const configure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configure?.apply(this, args);
            this.skebaChoiceRefresh?.();
            return result;
        };
    },
});
