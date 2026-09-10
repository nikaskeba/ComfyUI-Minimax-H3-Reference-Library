import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "SKEBA.MotionContextModes",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SKEBAMiniMaxH3MotionContext") return;
        const configure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configure?.apply(this, args);
            const mode = this.widgets?.find(w => w.name === "continuation_mode");
            // The selector occupies the former reinforcement boolean's slot.
            if (mode && typeof mode.value === "boolean") {
                mode.value = mode.value ? "pre-cut reinforcement" : "standard";
            }
            return result;
        };
    },
});
