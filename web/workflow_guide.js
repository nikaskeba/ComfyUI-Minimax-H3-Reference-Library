import { app } from "../../scripts/app.js";

const tags = new Set("a abbr b blockquote br caption code col colgroup dd del details div dl dt em figcaption figure h1 h2 h3 h4 h5 h6 hr i img kbd li mark ol p pre s samp section small span strong style sub summary sup table tbody td th thead tfoot tr u ul wbr".split(" "));
const discard = new Set("script iframe frame frameset object embed base meta link form input button textarea select option svg math template noscript".split(" "));
const attributes = new Set("style class id title alt width height colspan rowspan scope open start reversed type align valign".split(" "));

export function guideDocument(html) {
    // Template contents are inert. The iframe also blocks scripts and isolates CSS.
    const template = document.createElement("template");
    template.innerHTML = html;
    for (const element of [...template.content.querySelectorAll("*")]) {
        const tag = element.localName;
        if (discard.has(tag)) { element.remove(); continue; }
        if (!tags.has(tag)) { element.replaceWith(...element.childNodes); continue; }
        for (const attribute of [...element.attributes]) {
            const name = attribute.name;
            if (attributes.has(name)) continue;
            if (tag === "a" && name === "href" && /^(https?:\/\/|mailto:|#)/i.test(attribute.value.trim())) continue;
            if (tag === "img" && name === "src" && /^(https?:\/\/|data:image\/(png|jpeg|gif|webp);base64,)/i.test(attribute.value.trim())) continue;
            element.removeAttribute(name);
        }
        if (tag === "a" && element.hasAttribute("href") && !element.getAttribute("href").startsWith("#")) {
            element.setAttribute("target", "_blank"); element.setAttribute("rel", "noopener noreferrer");
        }
    }
    return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src https: http: data:; base-uri 'none'; form-action 'none'"><style>
    :root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;padding:16px;background:#171e28;color:#e4edf7;font:14px/1.55 system-ui;overflow-wrap:anywhere}h1,h2,h3{line-height:1.2}h1:first-child,h2:first-child,h3:first-child{margin-top:0}a{color:#8dd6ff}img{max-width:100%;height:auto}pre{white-space:pre-wrap;background:#101722;padding:10px;border-radius:5px}table{border-collapse:collapse;max-width:100%}td,th{border:1px solid #506078;padding:7px}summary{cursor:pointer}details{margin:8px 0}
    </style></head><body>${template.innerHTML}</body></html>`;
}

app.registerExtension({
    name: "SKEBA.WorkflowGuide",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaWorkflowGuide") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args), node = this;
            const html = this.widgets.find(widget => widget.name === "html");
            html.type = "converted-widget"; html.computeSize = () => [0, -4];
            if (html.inputEl) html.inputEl.style.display = "none";
            const root = document.createElement("div");
            root.style.cssText = "display:flex;flex-direction:column;height:100%;min-height:0;background:#171e28;border-radius:7px;overflow:hidden";
            const toolbar = document.createElement("div");
            toolbar.style.cssText = "display:flex;gap:8px;align-items:center;padding:7px;color:#a9bbd0;font:12px system-ui";
            const toggle = document.createElement("button"), hint = document.createElement("span");
            toggle.type = "button"; toggle.style.cssText = "background:#293c50;color:#e4edf7;border:1px solid #506078;border-radius:4px;padding:5px 10px;cursor:pointer";
            const source = document.createElement("textarea");
            source.setAttribute("aria-label", "Workflow guide HTML"); source.spellcheck = false;
            source.style.cssText = "flex:1;min-height:0;width:100%;box-sizing:border-box;resize:none;background:#101722;color:#e4edf7;border:0;padding:12px;font:13px/1.5 monospace";
            const frame = document.createElement("iframe"); frame.title = "Workflow guide preview";
            frame.setAttribute("sandbox", "allow-same-origin allow-popups allow-popups-to-escape-sandbox");
            frame.setAttribute("referrerpolicy", "no-referrer");
            frame.style.cssText = "flex:1;min-height:0;width:100%;border:0;background:#171e28";
            let editing = false;
            function show(edit) {
                editing = edit;
                source.style.display = edit ? "block" : "none"; frame.style.display = edit ? "none" : "block";
                toggle.textContent = edit ? "Preview" : "Edit HTML";
                hint.textContent = edit ? "Saved with the workflow · Ctrl/Cmd+Enter to preview" : "Double-click to edit";
                if (edit) { source.value = html.value || ""; source.focus(); }
                else frame.srcdoc = guideDocument(html.value || "");
            }
            source.oninput = () => { html.value = source.value; node.graph?.setDirtyCanvas(true, true); };
            source.onkeydown = event => {
                event.stopPropagation();
                if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); show(false); }
            };
            toggle.onclick = () => show(!editing);
            frame.onload = () => {
                frame.contentDocument?.addEventListener("dblclick", event => { event.preventDefault(); show(true); });
            };
            root.addEventListener("pointerdown", event => event.stopPropagation());
            root.addEventListener("wheel", event => event.stopPropagation());
            toolbar.append(toggle, hint); root.append(toolbar, source, frame);
            this.addDOMWidget("workflow_guide", "custom", root, {serialize:false, getMinHeight:()=>180});
            this.skebaGuideEdit = () => show(true);
            this.skebaGuideRestore = () => show(false);
            this.setSize([480, 400]); this.resizable = true;
            show(false);
            return result;
        };
        const configured = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configured?.apply(this, args); this.skebaGuideRestore?.(); return result;
        };
        const doubleClicked = nodeType.prototype.onDblClick;
        nodeType.prototype.onDblClick = function (...args) {
            this.skebaGuideEdit?.(); return doubleClicked?.apply(this, args);
        };
    },
});
