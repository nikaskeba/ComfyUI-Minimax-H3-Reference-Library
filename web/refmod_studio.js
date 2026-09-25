import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Copy only connected model dependencies; never queue the user's generation outputs.
export function modelGraph(output, nodeId, fields) {
    const candidates = Object.entries(output).filter(([id, node]) => node.class_type === "SkebaRefModStudio" && (!nodeId || id === nodeId));
    if (candidates.length !== 1) throw new Error("Open RefMod Library from the Studio node whose VAE connections you want to use.");
    const inputs = {}, prompt = {}, visiting = new Set();
    const link = value => Array.isArray(value) && value.length === 2 && Number.isInteger(value[1]);
    function copy(value) {
        if (!link(value)) return value;
        const id = String(value[0]), node = output[id], key = "workflow_" + id;
        if (!node) throw new Error("Unresolved workflow VAE connection: " + id);
        if (visiting.has(id)) throw new Error("Cycle in workflow VAE connections.");
        if (prompt[key]) return [key, value[1]];
        visiting.add(id);
        const data = node.inputs || {};
        let result;
        if (node.class_type === "Getter" || node.class_type === "Setter") {
            let source = data.inp ?? data.value ?? data.obj;
            if (node.class_type === "Getter" && !source) {
                const name = data.key ?? data.var_name;
                const setters = Object.values(output).filter(n => n.class_type === "Setter" && (n.inputs.key ?? n.inputs.var_name) === name);
                if (setters.length !== 1) throw new Error("Unresolved workflow VAE Getter: " + name);
                source = setters[0].inputs.value ?? setters[0].inputs.obj;
            }
            if (!link(source)) throw new Error("Connect the Studio VAE inputs to workflow VAE loaders.");
            result = copy(source);
        } else {
            prompt[key] = {class_type: node.class_type, inputs: Object.fromEntries(Object.entries(data).map(([name, v]) => [name, copy(v)]))};
            result = [key, value[1]];
        }
        visiting.delete(id);
        return result;
    }
    for (const field of fields) {
        const value = candidates[0][1].inputs[field];
        if (!link(value)) throw new Error(`Connect ${field === "vae" ? "video VAE" : "audio VAE"} to SKEBA RefMod Studio Create / Edit in the workflow.`);
        inputs[field] = copy(value);
    }
    return {prompt, inputs};
}

app.registerExtension({
    name: "SKEBA.RefModStudio.WorkflowModels",
    setup() {
        const channel = new BroadcastChannel("skeba-refmod-workflow");
        channel.onmessage = async ({data}) => {
            if (data.type !== "request-models" || (data.client && data.client !== api.clientId)) return;
            try {
                const {output} = await app.graphToPrompt();
                const result = modelGraph(output, data.node, data.fields);
                channel.postMessage({type: "models", id: data.id, ...result});
            } catch (error) {
                channel.postMessage({type: "models", id: data.id, error: error.message});
            }
        };
        window.addEventListener("pagehide", () => channel.close(), {once: true});
    },
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaRefModStudio") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            this.addWidget("button", "Open RefMod Library", null, () => {
                const url = new URL("h3-refmods", location.href);
                url.searchParams.set("client", api.clientId);
                url.searchParams.set("node", this.id);
                window.open(url.href, "_blank", "noopener");
            }, {serialize: false});
            return result;
        };
    },
});
