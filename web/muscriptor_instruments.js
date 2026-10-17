import { app } from "../../scripts/app.js";
import { FIELDS, restoredValues } from "./muscriptor_widget_state.js";

app.registerExtension({
    name: "Skeba.MuScriptorInstruments",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaMuScriptorGrid") return;
        const names = nodeData.input.optional?.instruments?.[1]?.instrumentOptions || [];
        if (!names.length) return;

        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            const node = this;
            const stored = node.widgets.find(widget => widget.name === "instruments");
            if (!stored) return result;
            stored.type = "converted-widget";
            stored.computeSize = () => [0, -4];
            if (stored.inputEl) stored.inputEl.hidden = true;

            const root = document.createElement("div");
            root.style.cssText = "height:100%;box-sizing:border-box;padding:8px;background:var(--comfy-menu-bg,#222);color:var(--input-text,#eee);font:13px system-ui;display:flex;flex-direction:column;gap:6px";
            const allLabel = document.createElement("label");
            allLabel.style.cssText = "display:flex;align-items:center;gap:7px;font-weight:600;cursor:pointer";
            const all = document.createElement("input");
            all.type = "checkbox";
            all.setAttribute("aria-label", "Check all instruments");
            const allText = document.createElement("span");
            allText.textContent = "Check all";
            allLabel.append(all, allText);

            const count = document.createElement("div");
            count.style.opacity = "0.75";
            const list = document.createElement("div");
            list.style.cssText = "overflow:auto;min-height:100px;max-height:260px;border:1px solid #555;border-radius:5px;padding:4px 7px";
            const rows = names.map(name => {
                const label = document.createElement("label");
                label.style.cssText = "display:flex;align-items:center;gap:7px;min-height:25px;cursor:pointer";
                const box = document.createElement("input");
                box.type = "checkbox";
                box.setAttribute("aria-label", name);
                const text = document.createElement("span");
                text.textContent = name.replaceAll("_", " ");
                label.append(box, text);
                list.append(label);
                return { name, box };
            });
            root.append(allLabel, count, list);

            const selected = () => {
                const value = String(stored.value || "").trim();
                if (!value) return new Set(names); // Existing blank values mean unrestricted.
                if (value === "__none__") return new Set();
                return new Set(value.split(/[\r\n,]+/).map(part => part.trim()).filter(Boolean));
            };
            const connected = () => node.inputs?.some(input =>
                (input.name === "instruments" || input.widget?.name === "instruments") && input.link != null);
            const refresh = () => {
                const active = selected();
                const checked = rows.filter(row => active.has(row.name)).length;
                all.checked = checked === rows.length;
                all.indeterminate = checked > 0 && checked < rows.length;
                all.disabled = connected();
                for (const row of rows) {
                    row.box.checked = active.has(row.name);
                    row.box.disabled = connected();
                }
                count.textContent = connected() ? "Controlled by connected input" : `${checked} of ${rows.length} selected`;
                node.graph?.setDirtyCanvas(true, true);
            };
            const save = active => {
                stored.value = active.size === names.length ? "" :
                    active.size ? names.filter(name => active.has(name)).join(", ") : "__none__";
                stored.callback?.(stored.value, node, stored);
                refresh();
            };
            all.addEventListener("change", () => save(all.checked ? new Set(names) : new Set()));
            for (const row of rows) row.box.addEventListener("change", () => {
                const active = selected();
                if (row.box.checked) active.add(row.name);
                else active.delete(row.name);
                save(active);
            });
            for (const event of ["pointerdown", "wheel", "keydown"]) {
                root.addEventListener(event, e => e.stopPropagation());
            }
            const picker = node.addDOMWidget("instrument_picker", "custom", root,
                { serialize: false, getMinHeight: () => 305 });
            picker.serialize = false;
            node.skebaRefreshInstruments = refresh;
            node.setSize([Math.max(node.size[0], 340), Math.max(node.size[1], 510)]);
            node.resizable = true;
            refresh();
            return result;
        };

        const configured = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (data, ...args) {
            const result = configured?.call(this, data, ...args);
            const values = restoredValues(data?.widgets_values, data?.widgets_values_named, names);
            FIELDS.forEach((field, index) => {
                const widget = this.widgets?.find(item => item.name === field);
                if (widget) widget.value = values[index];
            });
            this.skebaRefreshInstruments?.();
            return result;
        };
        const serialized = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function (data, ...args) {
            const result = serialized?.call(this, data, ...args);
            const values = FIELDS.map(field => this.widgets?.find(item => item.name === field)?.value);
            data.widgets_values = values;
            data.widgets_values_named = Object.fromEntries(FIELDS.map((field, index) => [field, values[index]]));
            return result;
        };
        const connectionsChanged = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (...args) {
            const result = connectionsChanged?.apply(this, args);
            this.skebaRefreshInstruments?.();
            return result;
        };
    },
});
