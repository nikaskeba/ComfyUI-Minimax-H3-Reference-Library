import { richPromptField } from "./prompt_rich_text.js";
import { app } from "../../scripts/app.js";

const sectionNames = {
    subject_definitions: "subject_definitions:", summary: "Summary", retention_analysis: "Retention analysis",
    detailed_description: "Description", timeline: "Timeline", overall_soundscape: "Soundscape", non_diegetic_music: "Music",
};
const template = "[s=15]\n\nsubject_definitions:\n\ndetailed_description:\n\ntimeline:\n\noverall_soundscape:\n\nnon_diegetic_music:\n";
function el(tag, text, className) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
}
export function parsePromptList(text) {
    return text.split("|").map((raw, index) => {
        const sections = [{heading: "", name: "Opening / definitions", text: ""}];
        const headings = /^[ \t]*(subject_definitions|summary|retention_analysis|detailed_description|timeline|overall_soundscape|non_diegetic_music)[ \t]*:[ \t]*/gim;
        let end = 0;
        for (const match of raw.matchAll(headings)) {
            sections.at(-1).text = raw.slice(end, match.index);
            sections.push({heading: match[0], name: sectionNames[match[1].toLowerCase()], text: ""});
            end = match.index + match[0].length;
        }
        sections.at(-1).text = raw.slice(end);
        const opening = sections[0].text;
        return {index, raw, sections, newLocation: /\[new_location\]/i.test(opening),
            seconds: opening.match(/\[s\s*=\s*([^\]\r\n]*)\]/i)?.[1],
            references: [...new Set(raw.match(/\{[^{}\n]+\}|§[^§\n]+§|<(?:character|location|object|voice|style):[^>\n]+>/g) || [])]};
    });
}
export function dialogueParts(text) {
    const parts = [], pattern = /<d>\[([^\]\r\n]+)\]([\s\S]*?)<\/d>/g;
    let end = 0;
    for (const match of text.matchAll(pattern)) {
        const header = match[1], voice = header.match(/§[^§\r\n]+§|<voice:[^>\r\n]+>/);
        const language = voice ? header.slice(0, voice.index).trim() : header.trim();
        if (!language || (voice && header.slice(voice.index + voice[0].length).trim()) || /<\/?d>/.test(match[2])) continue;
        parts.push({raw: text.slice(end, match.index)});
        parts.push({raw: match[0], language, speaker: voice?.[0] || "", words: match[2], dialogue: true});
        end = match.index + match[0].length;
    }
    parts.push({raw: text.slice(end)});
    return parts;
}

function visualEditor(root, widget, dirty) {
    let selected = 0, formatted = false, undo = [], redo = [], transaction = false;
    const tabs = el("div", undefined, "skeba-prompt-tabs"), rawButton = el("button", "Raw text"), viewButton = el("button", "Formatted view");
    const undoButton = el("button", "Undo"), redoButton = el("button", "Redo");
    const raw = el("textarea"), view = el("div", undefined, "skeba-prompt-view");
    raw.setAttribute("aria-label", "Prompt list separated by vertical bars");
    const timeline = el("div", undefined, "skeba-prompt-timeline"), overview = el("div", undefined, "skeba-prompt-muted"), fields = el("div");
    view.append(timeline, overview, fields);
    tabs.setAttribute("role", "tablist");
    for (const button of [rawButton, viewButton]) button.setAttribute("role", "tab");
    tabs.append(rawButton, viewButton, undoButton, redoButton); root.append(tabs, raw, view);
    function historyState() { undoButton.disabled = !undo.length; redoButton.disabled = !redo.length; }
    function write(value) {
        if (value === widget.value) return;
        if (!transaction) { undo.push({text: widget.value || "", selected}); if (undo.length > 100) undo.shift(); transaction = true; }
        redo = []; widget.value = value; raw.value = value; dirty(); historyState();
    }
    function replacePrompt(value) {
        const prompts = (widget.value || "").split("|"); prompts[selected] = value; write(prompts.join("|")); updateTimeline();
    }
    function action(callback) { transaction = false; callback(); transaction = false; }
    root.addEventListener("focusin", () => { transaction = false; });
    function historyStep(from, to) {
        const value = from.pop(); if (!value) return;
        to.push({text: widget.value || "", selected}); widget.value = value.text; selected = value.selected;
        transaction = false; raw.value = value.text; dirty(); render(); historyState();
    }
    undoButton.onclick = () => historyStep(undo, redo); redoButton.onclick = () => historyStep(redo, undo);
    function updateTimeline() {
        const prompts = parsePromptList(widget.value || ""), scroll = timeline.scrollLeft;
        selected = Math.min(selected, prompts.length - 1); timeline.replaceChildren();
        for (let i = 0; i <= prompts.length; i++) {
            const add = el("button", "+", "skeba-prompt-add"); add.setAttribute("aria-label", `Insert prompt at position ${i + 1}`);
            add.onclick = () => action(() => {
                const items = (widget.value || "").split("|"); items.splice(i, 0, template);
                write(items.join("|")); selected = i; render(); view.scrollTop = 0;
            }); timeline.append(add);
            if (i === prompts.length) break;
            const prompt = prompts[i], seconds = Number(prompt.seconds ?? 15);
            const block = el("button", undefined, "skeba-prompt-block");
            block.style.width = `${Math.max(115, Math.min(1800, (Number.isFinite(seconds) && seconds > 0 ? seconds : 15) * 10))}px`;
            block.classList.toggle("scene-break", prompt.newLocation); block.setAttribute("aria-pressed", String(i === selected));
            block.append(el("strong", `Prompt ${i + 1}`), el("span", prompt.seconds === undefined ? "15s · default" : `${prompt.seconds}s`));
            if (prompt.newLocation) block.append(el("span", "Scene change", "skeba-prompt-break"));
            if (!prompt.raw.trim()) block.append(el("small", "Empty segment"));
            block.onclick = () => { selected = i; transaction = false; render(); view.scrollTop = 0; }; timeline.append(block);
        }
        timeline.scrollLeft = scroll;
        const prompt = prompts[selected];
        overview.textContent = `Prompt ${selected + 1} of ${prompts.length} · References: ${prompt.references.join(" · ") || "None"}`;
    }
    function render() {
        if (!(widget.value || "").trim()) {
            timeline.replaceChildren(); overview.textContent = ""; fields.replaceChildren();
            const empty = el("div", undefined, "skeba-prompt-empty");
            const add = el("button", "Add first scene", "skeba-prompt-add"); add.type = "button";
            add.onclick = () => action(() => { write(template); selected = 0; render(); view.scrollTop = 0; });
            empty.append(el("p", "Start your prompt list with a new scene.", "skeba-prompt-muted"), add);
            fields.append(empty); historyState(); return;
        }
        updateTimeline(); fields.replaceChildren();
        const prompt = parsePromptList(widget.value || "")[selected];
        const save = () => replacePrompt(prompt.sections.map(s => s.heading + s.text).join(""));
        const settings = el("div", undefined, "skeba-prompt-settings"), lengthLabel = el("label", "Length (seconds) "), length = el("input"), sceneLabel = el("label", "Scene change "), scene = el("input"), error = el("p", "", "skeba-prompt-error");
        length.type = "number"; length.step = "any"; length.min = "0"; length.value = prompt.seconds ?? "15";
        scene.type = "checkbox"; scene.checked = prompt.newLocation;
        lengthLabel.append(length); sceneLabel.append(scene); settings.append(lengthLabel, sceneLabel);
        error.setAttribute("role", "status");
        const changeControl = (pattern, replacement) => {
            const opening = prompt.sections[0];
            if (pattern.test(opening.text)) { pattern.lastIndex = 0; let first = true; opening.text = opening.text.replace(pattern, () => { const next = first ? replacement : ""; first = false; return next; }); }
            else if (replacement) opening.text = replacement + " " + opening.text;
            save(); render();
        };
        length.onchange = () => {
            if (!length.value.trim() || !Number.isFinite(Number(length.value)) || Number(length.value) <= 0) { error.textContent = "Enter a positive duration. The previous length is unchanged."; length.setAttribute("aria-invalid", "true"); return; }
            action(() => changeControl(/\[s\s*=\s*[^\]\r\n]*\]/gi, `[s=${length.value}]`));
        };
        scene.onchange = () => action(() => changeControl(/\[new_location\]/gi, scene.checked ? "[new_location]" : ""));
        for (const [index, section] of prompt.sections.entries()) {
            const panel = el("section", undefined, "skeba-prompt-section"); panel.append(el("h4", section.name));
            const references = () => parsePromptList(widget.value || "")[selected]?.references || [];
            if (index === 0) {
                panel.append(settings, error);
                const pieces = section.text.split(/(\[new_location\]|\[s\s*=\s*[^\]\r\n]*\])/gi);
                pieces.forEach((piece, position) => {
                    if (!piece.trim() || /^\[(?:new_location|s\s*=)/i.test(piece)) return;
                    richPromptField(panel, piece, `${section.name} text`, value => {
                        pieces[position] = value; section.text = pieces.join(""); save();
                    }, references, dialogueParts, action);
                });
            } else {
                richPromptField(panel, section.text, `${section.name} text`, value => {
                    // Rich-text replacement can remove the newlines around a body.
                    // Section separators belong to the structure, not editable prose.
                    const newline = section.text.includes("\r\n") ? "\r\n" : "\n";
                    if (!/^[ \t]*\r?\n/.test(value)) value = newline + value;
                    if (index + 1 < prompt.sections.length) {
                        const ending = value.match(/(?:\r?\n[ \t]*)+$/)?.[0] || "";
                        const count = (ending.match(/\n/g) || []).length;
                        value += newline.repeat(Math.max(0, 2 - count));
                    }
                    section.text = value; save();
                }, references, dialogueParts, action);
            }
            fields.append(panel);
        }
        historyState();
    }
    function show(value) {
        formatted = value; raw.hidden = value; view.hidden = !value;
        rawButton.setAttribute("aria-selected", String(!value)); viewButton.setAttribute("aria-selected", String(value));
        raw.value = widget.value || ""; transaction = false; if (value) { render(); view.scrollTop = 0; }
    }
    raw.oninput = () => write(raw.value); rawButton.onclick = () => show(false); viewButton.onclick = () => show(true);
    root.addEventListener("keydown", event => {
        if (formatted && (event.ctrlKey || event.metaKey) && ["z", "y"].includes(event.key.toLowerCase())) {
            event.preventDefault(); event.stopPropagation();
            event.key.toLowerCase() === "y" || event.shiftKey ? historyStep(redo, undo) : historyStep(undo, redo);
        }
    });
    show(false); historyState();
    return () => { undo = []; redo = []; transaction = false; show(formatted); historyState(); };
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
        .skeba-prompt-break,.skeba-prompt-duration{font-size:11px;padding:3px 7px;border-radius:4px;background:#254859}
        .skeba-prompt-break{background:#65451e;color:#ffdfa0}
        .skeba-prompt-section{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.55;border-top:1px solid #2b394b;margin-top:12px}
        .skeba-prompt-section h4{color:#98caff;margin:10px 0 5px}
        .skeba-prompt-timeline{display:flex;gap:6px;overflow-x:auto;align-items:stretch;padding:8px 0 15px;position:sticky;top:-12px;background:#151c26;z-index:1}
        .skeba-prompt-block{flex:none;display:flex;flex-direction:column;gap:7px;text-align:left;padding:12px;background:#26384d;color:#edf6ff;border:1px solid #506681;border-radius:6px;cursor:pointer}
        .skeba-prompt-block[aria-pressed=true]{outline:2px solid #79cfff;outline-offset:-2px;background:#254b69}
        .skeba-prompt-block.scene-break{border-left:5px solid #efb964}
        .skeba-prompt-add{flex:none;background:#202f41;color:#b9e3ff;border:1px solid #506078;border-radius:6px;cursor:pointer}
        .skeba-prompt-empty{text-align:center;padding:28px 12px}.skeba-prompt-empty button{padding:10px 18px}
        .skeba-prompt-settings,.skeba-dialogue-card{display:flex;flex-wrap:wrap;gap:10px;white-space:normal}
        .skeba-prompt-editor label{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
        .skeba-prompt-editor input{min-width:0;max-width:100%;background:#111923;color:#e5edf6;border:1px solid #506078;border-radius:4px;padding:7px}
        .skeba-prompt-settings input[type=number]{width:95px}
        .skeba-prompt-section textarea{display:block;flex:none;min-height:60px;border:1px solid #35465b;border-radius:5px;margin:8px 0;resize:vertical}
        .skeba-prompt-section{white-space:normal}.skeba-prompt-error{color:#ffbd8c;white-space:normal;margin:5px 0}
        .skeba-dialogue-card{background:#183b37;border:1px solid #397b6d;border-radius:6px;padding:12px;margin:10px 0}
        .skeba-dialogue-card>strong,.skeba-dialogue-card textarea{width:100%}
        .skeba-prompt-tabs button:disabled{opacity:.4;cursor:default}
        .skeba-rich-tools{display:flex;gap:6px;margin:6px 0;flex-wrap:wrap}
        .skeba-rich-tools button,.skeba-reference-picker button{background:#26384d;color:#deefff;border:1px solid #506681;border-radius:4px;padding:5px 8px;cursor:pointer}
        .skeba-rich-text{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.9;background:#101923;border:1px solid #35465b;border-radius:6px;padding:10px;min-height:70px;outline:none}
        .skeba-rich-text:focus{border-color:#79cfff}
        .skeba-reference-token{color:#9cead3;background:#20433d;border-radius:3px;padding:1px 2px}
        .skeba-shot{display:inline-flex;align-items:center;gap:6px;background:#294b70;color:#c4e5ff;border-left:3px solid #72c5ff;border-radius:4px;padding:2px 7px;margin:3px 0;white-space:normal}
        .skeba-shot button,.skeba-inline-dialogue button{background:transparent;color:inherit;border:0;cursor:pointer}
        .skeba-inline-dialogue{display:inline-flex;flex-wrap:wrap;align-items:center;gap:5px;background:#193c37;border:1px solid #367d6c;border-radius:6px;padding:5px;max-width:100%;vertical-align:middle;white-space:normal}
        .skeba-inline-dialogue input{font-size:12px;padding:4px;width:170px}.skeba-inline-dialogue .skeba-dialogue-language{width:85px}
        .skeba-inline-dialogue textarea{display:inline-block!important;width:100%!important;min-height:34px!important;margin:0!important;padding:5px!important;font:13px/1.5 system-ui!important;resize:vertical}
        .skeba-prompt-section{position:relative}.skeba-reference-picker{position:absolute;top:35px;left:0;right:0;z-index:5;max-height:360px;overflow:auto;padding:12px;background:#1d2c3f;border:1px solid #75c7ef;border-radius:8px;box-shadow:0 8px 25px #0009;display:flex;gap:8px;flex-wrap:wrap}
        .skeba-reference-results{width:100%}.skeba-reference-results button{display:block;width:100%;text-align:left;margin:5px 0;overflow-wrap:anywhere}.skeba-reference-results h4{margin-top:10px}
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
            text.type = "converted-widget"; text.computeSize = () => [0, -4];
            if (text.inputEl) text.inputEl.style.display = "none";
            const root = el("div", undefined, "skeba-prompt-editor");
            this.skebaRefreshPromptText = visualEditor(root, text, () => this.graph?.setDirtyCanvas(true, true));
            root.addEventListener("pointerdown", event => event.stopPropagation());
            root.addEventListener("wheel", event => event.stopPropagation());
            this.addDOMWidget("prompt_list_editor", "custom", root, { serialize: false, getMinHeight: () => 350 });
            this.setSize([720, 680]);
            return result;
        };
        const configured = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            const result = configured?.apply(this, args); this.skebaRefreshPromptText?.(); return result;
        };
    },
});
