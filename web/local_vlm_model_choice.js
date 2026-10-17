import { app } from "../../scripts/app.js";

function savedPathToChoice(saved, choices) {
    const path = String(saved || "").replaceAll("\\", "/").toLowerCase();
    if (!/^(?:[a-z]:\/|\/)/.test(path)) return null;
    return choices.find(choice => path.endsWith(`/${String(choice).toLowerCase()}`)) || null;
}

app.registerExtension({
    name: "Skeba.LocalVLMModelChoice",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaH3LocalVLMLoader") return;
        const previous = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (data, ...args) {
            const result = previous?.call(this, data, ...args);
            const widget = this.widgets?.find(item => item.name === "model_folder");
            const choices = Array.isArray(widget?.options?.values) ? widget.options.values : [];
            const replacement = savedPathToChoice(widget?.value, choices);
            if (replacement) {
                widget.value = replacement;
                if (data?.widgets_values_named) data.widgets_values_named.model_folder = replacement;
                const index = this.widgets.indexOf(widget);
                if (Array.isArray(data?.widgets_values) && index < data.widgets_values.length)
                    data.widgets_values[index] = replacement;
            }
            return result;
        };
    },
});
