import assert from "node:assert/strict";
import fs from "node:fs";

class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.hidden = false; this.disabled = false; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    addEventListener() {}
    setAttribute() {}
}

const document = {createElement: tag => new Element(tag)};
const source = fs.readFileSync(new URL("../manager/reference-guide.js", import.meta.url), "utf8")
    .replaceAll("export function ", "function ");
const {renderReferenceGuide, referenceGuideText} = new Function(
    "document", source + "\nreturn {renderReferenceGuide, referenceGuideText};",
)(document);

const music = {tag: "Boards of Canada_rm", category: "music", reference_type: "music",
    is_refmod: true, has_visual: false, has_audio: true};
const character = {tag: "Kryten_BC", category: "character", reference_type: "character",
    built_in: true, actor: "Robert Llewellyn"};
const records = [music, character];
const full = referenceGuideText(records);
assert.match(full, /\{Boards of Canada_rm\}/);
assert.match(full, /Voice tag: §Boards of Canada_rm§/);
const noVoice = referenceGuideText(records, true, false);
assert.match(noVoice, /\{Boards of Canada_rm\}/);
assert.match(noVoice, /\{Kryten_BC\}/);
assert.doesNotMatch(noVoice, /Voice tag:/);

const elements = Object.fromEntries(["selection-empty", "selection-guide",
    "clear-selection", "copy-selection"].map(id => [id, new Element("div")]));
renderReferenceGuide(records, elements, null, false, false);
function allText(node) {
    return [node.textContent || "", ...node.children.flatMap(child =>
        child instanceof Element ? [allText(child)] : [])].join(" ");
}
const shown = allText(elements["selection-guide"]);
assert.match(shown, /\{Boards of Canada_rm\}/);
assert.match(shown, /\{Kryten_BC\}/);
assert.doesNotMatch(shown, /Voice: §/);
console.log("Reference Creator keeps audio-only brace tags and hides voice hints independently.");
