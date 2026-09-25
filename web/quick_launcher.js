import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

function matchingNodes(className) {
    const found = [], visited = new Set();
    function visit(graph) {
        if (!graph || visited.has(graph)) return;
        visited.add(graph);
        for (const node of graph._nodes || []) {
            if (node.comfyClass === className || node.type === className) found.push(node);
            if (node.subgraph) visit(node.subgraph);
        }
    }
    visit(app.graph);
    return found;
}

function runButton(node, name) {
    const widget = node.widgets?.find(item => item.type === "button" && item.name === name);
    if (!widget?.callback) {
        window.alert("The node's launcher button is unavailable. Refresh ComfyUI and try again.");
        return;
    }
    return widget.callback.call(widget, widget.value, app.canvas, node);
}

function chooseNode(nodes, action) {
    if (nodes.length === 1) return action(nodes[0]);
    const dialog = document.createElement("dialog");
    dialog.style.cssText = "background:#20242c;color:#eee;border:1px solid #555;border-radius:10px;padding:20px;min-width:300px";
    const title = document.createElement("h3");
    title.textContent = "Choose a workflow node";
    dialog.append(title);
    for (const node of nodes) {
        const button = document.createElement("button");
        button.textContent = `${node.title || node.type} (#${node.id})`;
        button.style.cssText = "display:block;width:100%;padding:10px;margin:6px 0";
        button.onclick = () => { dialog.close(); action(node); };
        dialog.append(button);
    }
    const cancel = document.createElement("button");
    cancel.textContent = "Cancel";
    cancel.onclick = () => dialog.close();
    dialog.append(cancel);
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    document.body.append(dialog);
    dialog.showModal();
}

app.registerExtension({
    name: "SKEBA.QuickLauncher",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaQuickLauncher") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            this.addWidget("button", "Open Live Playlist", null, () => {
                const nodes = matchingNodes("SkebaSaveClipToFile");
                if (nodes.length) return chooseNode(nodes, node => runButton(node, "Open Live Playlist"));
                const url = new URL("h3-video-playlist", window.location.href);
                if (api.clientId) url.searchParams.set("client_id", api.clientId);
                window.open(url.href, "_blank", "noopener");
            }, { serialize: false });
            this.addWidget("button", "Open Reference Library", null, () => {
                window.open(`${window.location.origin}/h3-references`, "_blank", "noopener");
            }, { serialize: false });
            this.addWidget("button", "Register / Update playlist workflow", null, () => {
                const nodes = matchingNodes("SkebaPlaylistWorkflow");
                if (!nodes.length) {
                    window.alert("Add and connect SKEBA Playlist Workflow — Register / Update in this workflow first.");
                    return;
                }
                return chooseNode(nodes, node => runButton(node, "Register / Update playlist workflow"));
            }, { serialize: false });
            this.setSize([320, this.computeSize()[1]]);
            return result;
        };
    },
});
