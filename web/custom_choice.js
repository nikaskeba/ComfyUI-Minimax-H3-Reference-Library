import { app } from "../../scripts/app.js";
import { setWidgetConfig } from "../../extensions/core/widgetInputs.js";

export function parseChoices(text) {
    return [...new Set(String(text).split(/[\r\n,]+/).map(value => value.trim()).filter(Boolean))];
}

app.registerExtension({
    name: "Skeba.CustomChoice",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaCustomChoice") return;
        // UI-only combo; Python keeps STRING so choices remain per-instance.
        nodeData.input.required.selected = [parseChoices(nodeData.input.required.choices[1].default), {default: "22"}];
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            const choices = this.widgets.find(widget => widget.name === "choices");
            const selected = this.widgets.find(widget => widget.name === "selected");
            choices.type = "converted-widget";
            choices.computeSize = () => [0, -4];
            if (choices.inputEl) choices.inputEl.hidden = true;
            const root = document.createElement("div");
            root.style.cssText = "padding:8px;box-sizing:border-box;display:grid;gap:8px;color:var(--input-text,#eee);font:13px system-ui;background:var(--comfy-menu-bg,#222);height:100%;overflow:auto";
            selected.type = "combo";
            const edit = document.createElement("button"); edit.textContent = "Edit choices";
            const panel = document.createElement("div"); panel.hidden = true;
            const hint = document.createElement("p"); hint.textContent = "One choice per line (or comma-separated). Values must match the target node exactly. Expose selected as a subgraph input to show these choices on the outer node.";
            const input = document.createElement("textarea"); input.rows = 5; input.setAttribute("aria-label", "Custom choices");
            input.style.cssText = "width:100%;box-sizing:border-box;resize:vertical";
            const error = document.createElement("div"); error.setAttribute("role", "alert"); error.style.color = "#ff9292";
            const apply = document.createElement("button"); apply.textContent = "Apply choices";
            const cancel = document.createElement("button"); cancel.textContent = "Cancel";
            const dirty = () => this.graph?.setDirtyCanvas(true, true);
            const refresh = () => {
                const values = parseChoices(choices.value);
                selected.options = {...selected.options, values};
                let socket = this.inputs?.find(input => input.widget?.name === "selected" || input.name === "selected");
                if (!socket) socket = this.addInput("selected", "COMBO", {widget: {name: "selected"}});
                socket.type = "COMBO";
                socket.widget ??= {name: "selected"};
                setWidgetConfig(socket, [values, {default: selected.value}]);
                const rootGraph = this.graph?.rootGraph;
                if (rootGraph && this.graph !== rootGraph) {
                    for (const graph of [rootGraph, ...rootGraph.subgraphs.values()]) {
                        for (const host of graph.nodes) {
                            if (host.subgraph !== this.graph) continue;
                            host.rebuildInputWidgetBindings();
                        }
                    }
                }
                // Preserve invalid saved values for backend validation, not silent substitution.
            };
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
            panel.append(hint, input, error, apply, cancel); root.append(edit, panel);
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
