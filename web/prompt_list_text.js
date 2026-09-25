import { app } from "../../scripts/app.js";

const sectionNames = {
    subject_definitions: "Subjects & wardrobe",
    summary: "Summary",
    retention_analysis: "Retention analysis",
    detailed_description: "Description",
    timeline: "Timeline",
    overall_soundscape: "Soundscape",
    non_diegetic_music: "Music",
};

export function parsePromptList(text) {
    return text.split("|").map((raw, index) => {
        const sections = [];
        let current = { name: "Opening / definitions", text: "" };
        for (const line of raw.split(/\r?\n/)) {
            const heading = line.trim().match(/^(subject_definitions|summary|retention_analysis|detailed_description|timeline|overall_soundscape|non_diegetic_music)\s*:\s*(.*)$/i);
            if (heading) {
                if (current.text.trim()) sections.push(current);
                current = { name: sectionNames[heading[1].toLowerCase()], text: heading[2] };
            } else current.text += (current.text ? "\n" : "") + line;
        }
        if (current.text.trim()) sections.push(current);
        const references = [...new Set(raw.match(/\{[^{}\n]+\}|§[^§\n]+§|<(?:character|location|object|voice|style):[^>\n]+>/g) || [])];
        return { index, empty: !raw.trim(), newLocation: /\[new_location\]/i.test(raw),
            seconds: raw.match(/\[s\s*=\s*([\d.]+)\]/i)?.[1], references, sections };
    });
}

function el(tag, text, className) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
}

function highlight(text) {
    const fragment = document.createDocumentFragment();
    const tokens = /(\[Shot\s+\d+\]|\[new_location\]|\[s\s*=\s*[\d.]+\]|\{[^{}\n]+\}|§[^§\n]+§|<(?:character|location|object|voice|style):[^>\n]+>)/gi;
    let start = 0;
    for (const match of text.matchAll(tokens)) {
        fragment.append(document.createTextNode(text.slice(start, match.index)));
        fragment.append(el("mark", match[0]));
        start = match.index + match[0].length;
    }
    fragment.append(document.createTextNode(text.slice(start)));
    return fragment;
}

export function renderPromptList(container, text) {
    container.replaceChildren();
    const prompts = parsePromptList(text);
    container.append(el("p", `${prompts.filter(p => !p.empty).length} prompts · separated by | · read-only preview`, "skeba-prompt-muted"));
    for (const prompt of prompts) {
        const card = el("details", undefined, "skeba-prompt-card");
        card.open = true;
        const title = el("summary", `Prompt ${prompt.index + 1}`);
        if (prompt.newLocation) title.append(el("span", "New location", "skeba-prompt-break"));
        title.append(el("span", prompt.seconds ? `${prompt.seconds}s` : "Default duration", "skeba-prompt-duration"));
        card.append(title);
        if (prompt.empty) card.append(el("p", "Empty segment — text is preserved unchanged.", "skeba-prompt-muted"));
        if (prompt.references.length) {
            const refs = el("details", undefined, "skeba-prompt-refs");
            refs.append(el("summary", "References used"));
            for (const ref of prompt.references) refs.append(el("code", ref));
            card.append(refs);
        }
        for (const section of prompt.sections) {
            const body = el("div", undefined, "skeba-prompt-section");
            body.append(el("h4", section.name));
            const content = el("div");
            content.append(highlight(section.text.trim()));
            body.append(content);
            card.append(body);
        }
        container.append(card);
    }
}

app.registerExtension({
    name: "SKEBA.PromptListText",
    setup() {
        const style = el("style");
        style.textContent = `
        .skeba-prompt-editor{height:100%;display:flex;flex-direction:column;min-height:0;background:#151c26;color:#e5edf6;border-radius:8px;overflow:hidden;font:13px system-ui}
        .skeba-prompt-tabs{display:flex;gap:8px;padding:9px;border-bottom:1px solid #38465a}
        .skeba-prompt-tabs button{padding:7px 12px;border:1px solid #506078;border-radius:5px;background:#253144;color:#eee;cursor:pointer}
        .skeba-prompt-tabs button[aria-selected=true]{background:#28587c;border-color:#73bcec}
        .skeba-prompt-editor textarea{flex:1;min-height:0;width:100%;box-sizing:border-box;resize:none;border:0;padding:12px;background:#111923;color:#e5edf6;font:13px/1.5 monospace}
        .skeba-prompt-view{flex:1;overflow:auto;min-height:0;padding:12px;user-select:text}
        .skeba-prompt-editor [hidden]{display:none!important}
        .skeba-prompt-card{margin-bottom:14px;border:1px solid #3d5069;border-radius:7px;padding:12px}
        .skeba-prompt-card>summary{font-weight:700;cursor:pointer;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
        .skeba-prompt-break,.skeba-prompt-duration{font-size:11px;padding:3px 7px;border-radius:4px;background:#254859}
        .skeba-prompt-break{background:#65451e;color:#ffdfa0}
        .skeba-prompt-section{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.55;border-top:1px solid #2b394b;margin-top:12px}
        .skeba-prompt-section h4{color:#98caff;margin:10px 0 5px}
        .skeba-prompt-editor mark{color:#9fedd3;background:#20443e;border-radius:3px;padding:0 2px}
        .skeba-prompt-muted{color:#a2b2c5}.skeba-prompt-refs{margin-top:12px}.skeba-prompt-refs code{display:block;overflow-wrap:anywhere;color:#9fedd3;margin:5px 0}
        `;
        document.head.append(style);
    },
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "SkebaPromptListText") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = created?.apply(this, args);
            const text = this.widgets.find(widget => widget.name === "text");
            text.type = "converted-widget";
            text.computeSize = () => [0, -4];
            if (text.inputEl) text.inputEl.style.display = "none";
            const root = el("div", undefined, "skeba-prompt-editor"), tabs = el("div", undefined, "skeba-prompt-tabs");
            const rawButton = el("button", "Raw text"), viewButton = el("button", "Formatted view");
            const input = el("textarea"), view = el("div", undefined, "skeba-prompt-view");
            input.setAttribute("aria-label", "Prompt list separated by vertical bars");
            input.placeholder = "Paste prompts separated by |";
            input.value = text.value || "";
            tabs.setAttribute("role", "tablist");
            for (const button of [rawButton, viewButton]) { button.type = "button"; button.setAttribute("role", "tab"); }
            const show = formatted => {
                input.hidden = formatted; view.hidden = !formatted;
                rawButton.setAttribute("aria-selected", String(!formatted)); viewButton.setAttribute("aria-selected", String(formatted));
                if (formatted) renderPromptList(view, text.value || "");
            };
            input.oninput = () => { text.value = input.value; this.graph?.setDirtyCanvas(true, true); };
            rawButton.onclick = () => show(false); viewButton.onclick = () => show(true);
            root.addEventListener("pointerdown", event => event.stopPropagation());
            root.addEventListener("wheel", event => event.stopPropagation());
            tabs.append(rawButton, viewButton); root.append(tabs, input, view);
            this.addDOMWidget("prompt_list_editor", "custom", root, { serialize: false, getMinHeight: () => 300 });
            this.skebaRefreshPromptText = () => { input.value = text.value || ""; if (!view.hidden) renderPromptList(view, input.value); };
            show(false);
            this.setSize([620, 580]);
            return result;
        };
        const configured = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configured?.apply(this, args);
            this.skebaRefreshPromptText?.();
            return result;
        };
    },
});
