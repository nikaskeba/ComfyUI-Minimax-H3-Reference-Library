import assert from "node:assert/strict";
import fs from "node:fs";

class Element {
    constructor() { this.style = {}; this.children = []; this.events = {}; }
    append(...children) { this.children.push(...children); }
    setAttribute() {}
    setCustomValidity(value) { this.validity = value; }
    addEventListener(name, callback) { this.events[name] = callback; }
}
let extension;
const app = { registerExtension(value) { extension = value; } };
const document = { createElement() { return new Element(); } };
const source = fs.readFileSync(new URL("../web/fixed_palette.js", import.meta.url), "utf8").replace(/^import .*;\r?\n/, "");
new Function("app", "document", source)(app, document);
class Node {
    constructor() {
        this.widgets = [{ name: "number_of_colors", value: 3 }, ...Array.from({length: 16}, (_, i) => ({name: `color_${i+1}`, value: ["#00FF00", "#000000", "#FFFFFF"][i] || "#FFFFFF"}))];
        this.size = [300, 100];
    }
    addDOMWidget(name, type, root, options) { this.root = root; const w = {name, type, options}; this.widgets.push(w); return w; }
    computeSize() { return [300, 100]; }
    setSize(size) { this.size = size; }
}
await extension.beforeRegisterNodeDef(Node, {name: "SkebaFixedPaletteQuantize"});
const node = new Node(); node.onNodeCreated();
const visible = n => n.root.children.filter(row => row.style.display !== "none").length;
assert.equal(visible(node), 3);
node.widgets[0].value = 16; node.widgets[0].callback();
const last = node.root.children[15];
last.children[1].value = "#123456"; last.children[1].events.input();
assert.equal(node.widgets[16].value, "#123456");
node.widgets[0].value = 2; node.widgets[0].callback();
assert.equal(visible(node), 2);
const saved = JSON.parse(JSON.stringify(node.widgets.slice(0,17).map(w => w.value)));
const restored = new Node(); restored.onNodeCreated();
saved.forEach((value, i) => { restored.widgets[i].value = value; }); restored.onConfigure();
assert.equal(visible(restored), 2);
restored.widgets[0].value = 16; restored.widgets[0].callback();
assert.equal(restored.root.children[15].children[2].value, "#123456");
assert.equal(restored.widgets[16].value, "#123456");
console.log("Picker synchronization, count visibility, and widget-value save/load passed");
