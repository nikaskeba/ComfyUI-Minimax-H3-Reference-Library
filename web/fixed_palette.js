import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "SKEBA.FixedPalette",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaFixedPaletteQuantize") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            const node = this;
            const count = node.widgets.find(w => w.name === "number_of_colors");
            const root = document.createElement("div");
            root.style.cssText = "display:flex;flex-direction:column;gap:4px;padding:6px;box-sizing:border-box;background:var(--comfy-menu-bg,#222);color:var(--input-text,#ddd);";
            const rows = [];
            for (let i = 1; i <= 16; i++) {
                const stored = node.widgets.find(w => w.name === `color_${i}`);
                // Keep the original widget and its serialization position; only replace its presentation.
                stored.type = "palette_hidden";
                stored.computeSize = () => [0, -4];
                stored.draw = () => {};
                const row = document.createElement("label");
                row.style.cssText = "display:flex;align-items:center;gap:6px;height:28px;";
                const name = document.createElement("span");
                name.textContent = `Color ${i}`;
                name.style.width = "58px";
                const picker = document.createElement("input");
                picker.type = "color";
                picker.setAttribute("aria-label", `Color ${i} picker`);
                picker.style.cssText = "width:38px;height:26px;padding:0;border:0;";
                const hex = document.createElement("input");
                hex.type = "text";
                hex.setAttribute("aria-label", `Color ${i} hex`);
                hex.style.cssText = "min-width:0;flex:1;width:90px;";
                const sync = () => {
                    hex.value = stored.value;
                    const value = String(stored.value).trim().replace(/^#/, "");
                    if (/^[0-9a-f]{6}$/i.test(value)) picker.value = `#${value}`;
                };
                const commit = value => {
                    const clean = value.trim().replace(/^#/, "");
                    const valid = /^[0-9a-f]{6}$/i.test(clean);
                    hex.setCustomValidity(valid ? "" : "Enter #RRGGBB");
                    stored.value = valid ? `#${clean.toUpperCase()}` : value;
                    sync();
                    node.graph?.setDirtyCanvas(true, true);
                };
                picker.addEventListener("input", () => commit(picker.value));
                hex.addEventListener("change", () => commit(hex.value));
                row.append(name, picker, hex);
                root.append(row);
                rows.push({ row, sync });
            }
            const panel = node.addDOMWidget("palette_editor", "palette_editor", root, { serialize: false });
            panel.computeSize = () => [260, Math.max(2, Math.min(16, Number(count.value))) * 32 + 12];
            const refresh = () => {
                rows.forEach(({ row, sync }, i) => {
                    row.style.display = i < Number(count.value) ? "flex" : "none";
                    sync();
                });
                node.setSize([Math.max(node.size[0], 300), node.computeSize()[1]]);
                node.graph?.setDirtyCanvas(true, true);
            };
            const changed = count.callback;
            count.callback = function (...values) { changed?.apply(this, values); refresh(); };
            const configured = node.onConfigure;
            node.onConfigure = function (...values) { const r = configured?.apply(this, values); refresh(); return r; };
            refresh();
            return result;
        };
    },
});
