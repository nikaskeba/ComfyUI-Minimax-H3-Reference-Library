import { api } from "../../scripts/api.js";

function element(tag, text, cls) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
}

// Only editor-created atoms carry raw syntax; pasted HTML is never accepted.
function readText(node) {
    if (node.nodeType === Node.TEXT_NODE) return node.nodeValue;
    if (node.nodeType !== Node.ELEMENT_NODE) return "";
    if (node.hasAttribute("data-prompt-raw")) return node.dataset.promptRaw;
    if (node.tagName === "BR") return "\n";
    let text = "";
    for (const child of node.childNodes) {
        if (child.nodeType === Node.ELEMENT_NODE && ["DIV", "P"].includes(child.tagName) && text && !text.endsWith("\n")) text += "\n";
        text += readText(child);
    }
    return text;
}

export function richPromptField(parent, text, label, changed, references, dialogueParts, runAction = callback => callback()) {
    const bar = element("div", undefined, "skeba-rich-tools");
    const editor = element("div", undefined, "skeba-rich-text");
    editor.contentEditable = "true";
    editor.setAttribute("role", "textbox"); editor.setAttribute("aria-multiline", "true"); editor.setAttribute("aria-label", label);
    const notice = element("p", "", "skeba-prompt-error"); notice.setAttribute("role", "status");
    let range = null;
    function remember() {
        const selection = window.getSelection();
        if (selection.rangeCount && editor.contains(selection.anchorNode) && !selection.anchorNode.parentElement?.closest("[data-prompt-raw]")) range = selection.getRangeAt(0).cloneRange();
    }
    function commit() {
        const value = readText(editor);
        if (value.includes("|")) { notice.textContent = "Use + to insert a prompt, or edit separators in Raw text. Remove | to save this field."; return false; }
        notice.textContent = dialogueParts(value).some(p => !p.dialogue && /<\/?d>/.test(p.raw)) ? "Unrecognized dialogue markup is kept as text. You can edit it here." : "";
        changed(value); return true;
    }
    function insert(node) {
        editor.focus();
        const target = range && editor.contains(range.commonAncestorContainer) ? range : document.createRange();
        if (target !== range) { target.selectNodeContents(editor); target.collapse(false); }
        target.deleteContents(); target.insertNode(node); target.setStartAfter(node); target.collapse(true);
        const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(target); range = target.cloneRange();
        commit();
    }
    function button(text, name, action, container = bar) {
        const button = element("button", text); button.type = "button"; button.setAttribute("aria-label", name);
        button.onmousedown = event => { remember(); event.preventDefault(); };
        button.onclick = event => { event.preventDefault(); event.stopPropagation(); runAction(action); };
        container.append(button); return button;
    }
    function renumberShots() {
        editor.querySelectorAll('.skeba-shot').forEach((shot, index) => {
            shot.dataset.promptRaw = `[Shot ${index + 1}]`; shot.querySelector('strong').textContent = `Shot ${index + 1}`;
        });
    }
    function shot(raw) {
        const atom = element("span", undefined, "skeba-shot"); atom.contentEditable = "false"; atom.dataset.promptRaw = raw;
        atom.append(element("strong", raw.slice(1, -1)));
        button("×", "Remove shot marker", () => { atom.remove(); renumberShots(); commit(); }, atom);
        return atom;
    }
    function dialogue(part) {
        const atom = element("span", undefined, "skeba-inline-dialogue"); atom.contentEditable = "false"; atom.dataset.promptRaw = part.raw;
        atom.append(element("span", "💬"));
        const language = element("input"), speaker = element("input"), words = element("textarea");
        language.value = part.language; language.setAttribute("aria-label", "Dialogue language"); language.className = "skeba-dialogue-language";
        speaker.value = part.speaker; speaker.setAttribute("aria-label", "Dialogue speaker"); speaker.placeholder = "Speaker (optional)";
        words.value = part.words; words.rows = 1; words.setAttribute("aria-label", "Dialogue speech");
        const choices = element("datalist"); choices.id = `speakers-${Math.random().toString(36).slice(2)}`;
        for (const ref of references()) {
            const value = /^§|^<voice:/.test(ref) ? ref : /^\{/.test(ref) ? `§${ref.slice(1, -1)}§` : null;
            if (value) { const option = element("option"); option.value = value; choices.append(option); }
        }
        speaker.setAttribute("list", choices.id);
        function update() {
            const lang = language.value.trim(), entered = speaker.value.trim(), voice = entered && !/^[§<]/.test(entered) ? `§${entered}§` : entered;
            if (!lang || /[\[\]<>§|\r\n]/.test(lang) || (voice && !/^(§[^§\r\n|]+§|<voice:[^>\r\n|]+>)$/.test(voice)) || /<\/?d>|\|/.test(words.value)) {
                notice.textContent = "Enter a language, an optional voice tag/name, and speech without | or dialogue wrapper tags. Last valid text is retained."; return;
            }
            atom.dataset.promptRaw = `<d>[${lang}${voice ? " " + voice : ""}]${words.value}</d>`; commit();
        }
        for (const input of [language, speaker, words]) {
            input.oninput = event => { event.stopPropagation(); update(); };
            input.onkeydown = event => { if (!["z", "y"].includes(event.key.toLowerCase()) || !(event.ctrlKey || event.metaKey)) event.stopPropagation(); };
        }
        atom.append(language, speaker, choices);
        button("×", "Remove dialogue", () => { atom.remove(); commit(); }, atom);
        atom.append(words);
        return atom;
    }
    function highlight(value) {
        const pattern = /\[Shot\s+\d+\]|\{[^{}\r\n]+\}|§[^§\r\n]+§|<(?:character|location|object|voice|style):[^>\r\n]+>/gi;
        let start = 0;
        for (const match of value.matchAll(pattern)) {
            editor.append(document.createTextNode(value.slice(start, match.index)));
            editor.append(/^\[Shot/i.test(match[0]) ? shot(match[0]) : element("span", match[0], "skeba-reference-token")); start = match.index + match[0].length;
        }
        editor.append(document.createTextNode(value.slice(start)));
    }
    function paint(value) {
        editor.replaceChildren();
        for (const part of dialogueParts(value)) part.dialogue ? editor.append(dialogue(part)) : highlight(part.raw);
    }
    paint(text);
    if (dialogueParts(text).some(p => !p.dialogue && /<\/?d>/.test(p.raw))) notice.textContent = "Unrecognized dialogue markup is kept as text. You can edit it here.";
    editor.oninput = () => commit(); editor.onkeyup = remember; editor.onmouseup = remember;
    editor.onkeydown = event => {
        if (event.target !== editor) return;
        if (event.key === "Enter") { event.preventDefault(); remember(); insert(document.createTextNode("\n")); }
    };
    editor.onpaste = event => {
        if (event.target !== editor) return;
        event.preventDefault(); remember(); insert(document.createTextNode(event.clipboardData.getData("text/plain")));
    };
    editor.ondrop = event => { event.preventDefault(); remember(); insert(document.createTextNode(event.dataTransfer.getData("text/plain"))); };
    editor.addEventListener("focusout", () => {
        // Reapply highlighting after plain-text edits, but never interrupt inline inputs.
        setTimeout(() => { if (editor.isConnected && !editor.contains(document.activeElement) && !parent.querySelector('.skeba-reference-picker') && commit()) { paint(readText(editor)); range = null; } }, 0);
    });
    if (["Timeline text", "Description text"].includes(label)) {
    button("+ Shot", "Add shot", () => { insert(shot("[Shot 1]")); renumberShots(); commit(); });
    button("+ Dialogue", "Add dialogue", () => {
        const atom = dialogue({raw:"<d>[English]</d>", language:"English", speaker:"", words:""}); insert(atom); atom.querySelector('textarea').focus();
    });
    }
    button("+ Reference", "Add reference", () => openPicker());
    async function openPicker() {
        if (parent.querySelector('.skeba-reference-picker')) return;
        const popup = element("div", undefined, "skeba-reference-picker"); popup.contentEditable = "false"; popup.setAttribute("role", "dialog"); popup.setAttribute("aria-label", "Insert reference");
        const search = element("input"), filter = element("select"), results = element("div", undefined, "skeba-reference-results"), status = element("p");
        search.placeholder = "Search characters, locations, objects…"; search.setAttribute("aria-label", "Search references"); filter.setAttribute("aria-label", "Reference type");
        for (const type of ["all", "character", "location", "object", "music", "video", "voice"]) { const option = element("option", type === "all" ? "All types" : type); option.value = type; filter.append(option); }
        popup.append(element("strong", "Insert reference"), search, filter);
        button("Close", "Close reference picker", () => { popup.remove(); editor.focus(); }, popup);
        popup.append(element("small", "Inserts at the cursor. Add the reference to subject_definitions too when needed."), status, results); parent.append(popup);
        let catalog = [], loaded = false;
        function draw() {
            if (!popup.isConnected) return;
            results.replaceChildren();
            const query = search.value.toLowerCase();
            const current = references().map(tag => ({tag:tag.replace(/ = [\s\S]*>$/, ">"), name:tag, type: /^<(\w+):/.exec(tag)?.[1] || "", linked:true}));
            const seen = new Set();
            for (const group of [{name:"In this prompt / selected", rows:[...current,...catalog.filter(r=>r.linked)]},{name:"Library", rows:catalog.filter(r=>!r.linked)}]) {
                const rows = group.rows.filter(row => {
                    if (seen.has(row.tag) || !(row.name+row.tag).toLowerCase().includes(query) || (filter.value !== "all" && row.type && row.type !== filter.value)) return false;
                    seen.add(row.tag); return true;
                });
                if (!rows.length) continue;
                results.append(element("h4", group.name));
                for (const row of rows.slice(0,100)) button(row.name, `Insert ${row.tag}`, () => {
                    popup.remove(); insert(element("span", row.tag, "skeba-reference-token"));
                }, results);
                if (rows.length > 100) results.append(element("small", "Showing first 100 matches; narrow your search."));
            }
            if (!results.childNodes.length) results.textContent = loaded ? "No matching references." : "Loading library…";
        }
        search.oninput = draw; filter.onchange = draw; popup.onkeydown = event => { event.stopPropagation(); if (event.key === "Escape") popup.remove(); }; draw(); search.focus();
        const endpoints = ['/api/h3-references/records','/api/h3-built-in-references/records'];
        const replies = await Promise.allSettled(endpoints.map(async path => { const response = await api.fetchApi(path); if (!response.ok) throw Error('Library could not be loaded'); return response.json(); }));
        const saved = new Set(JSON.parse(localStorage.getItem('skeba-reference-selection') || '[]')), builtins = new Set(JSON.parse(localStorage.getItem('skeba-built-in-selection') || '[]'));
        replies.forEach((reply,index) => {
            if (reply.status !== 'fulfilled') return;
            for (const record of reply.value.records || []) {
                const name = index ? record.library_tag || `${record.tag}_BC` : record.tag;
                const voiceOnly = !index && record.reference_type === 'voice';
                catalog.push({tag:voiceOnly ? `§${name}§` : `{${name}}`, name:record.name || name, type:index?'character':record.reference_type || record.category, linked:index?builtins.has(record.tag):saved.has(record.id)});
            }
        });
        loaded = true; status.textContent = replies.some(r=>r.status==='rejected') ? 'Some library entries could not load. Current prompt references are still available.' : '';
        draw();
    }
    parent.append(bar, editor, notice);
    return editor;
}
