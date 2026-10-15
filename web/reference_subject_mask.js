import { app } from "../../scripts/app.js";

const HUMAN_REGIONS = ["whole person", "face", "head", "lips"];
const OBJECT_REGIONS = ["whole object"];

function syncRegion(node, number) {
    const kind = node.widgets?.find(widget => widget.name === `subject_${number}_kind`);
    const region = node.widgets?.find(widget => widget.name === `subject_${number}_region`);
    if (!kind || !region) return;
    const values = kind.value === "object" ? OBJECT_REGIONS : HUMAN_REGIONS;
    region.options = { ...region.options, values };
    if (!values.includes(region.value)) region.value = values[0];
    node.graph?.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "Skeba.ReferenceSubjectMaskRegions",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaPersonReferenceMask") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            for (const number of [1, 2]) {
                const kind = this.widgets?.find(widget => widget.name === `subject_${number}_kind`);
                if (!kind) continue;
                const original = kind.callback;
                kind.callback = (...callbackArgs) => {
                    const value = original?.apply(kind, callbackArgs);
                    queueMicrotask(() => syncRegion(this, number));
                    return value;
                };
                syncRegion(this, number);
            }
            return result;
        };
        const configured = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configured?.apply(this, args);
            syncRegion(this, 1);
            syncRegion(this, 2);
            return result;
        };
    },
});
