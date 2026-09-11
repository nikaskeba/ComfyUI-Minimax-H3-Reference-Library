import assert from "node:assert/strict";
import fs from "node:fs";

class Element {
    constructor() { this.style = {}; this.children = []; this.events = {}; }
    append(...children) { this.children.push(...children); }
    setAttribute() {}
    setCustomValidity(value) { this.validity = value; }
    addEventListener(name, callback) { this.events[name] = callback; }
    getBoundingClientRect() { return {left: 0, top: 0, width: 400, height: 200}; }
}
let extension;
let queued, sampled;
const app = { registerExtension(value) { extension = value; }, async graphToPrompt() {
    return {output: {"7": {class_type: "SkebaFixedPaletteQuantize", inputs: {image: ["1",0]}},
        "1": {class_type: "LoadImage", inputs: {}}, "9": {class_type: "SaveVideo", inputs: {video:["7",0]}}}, workflow: {}};
} };
const api = { apiURL: value => value, async queuePrompt(_, prompt) { queued = prompt; },
    async fetchApi(_, options) { sampled = JSON.parse(options.body); return {ok:true, async json() {
        return {hex:"#0CE712", x:4, y:2, rgb:[12,231,18]};
    }}; }};
const document = { createElement() { return new Element(); } };
const previewSource = fs.readFileSync(new URL("../web/palette_preview.js", import.meta.url), "utf8").replace(/^import .*;\r?\n/gm, "").replaceAll("export function", "function");
const attachPreview = new Function("api", "document", previewSource + "\nreturn attachPreview;")(api, document);
const source = fs.readFileSync(new URL("../web/fixed_palette.js", import.meta.url), "utf8").replace(/^import .*;\r?\n/gm, "");
new Function("app", "document", "attachPreview", source)(app, document, attachPreview);
class Node {
    constructor() {
        this.widgets = [{ name: "number_of_colors", value: 3 }, ...Array.from({length: 16}, (_, i) => ({name: `color_${i+1}`, value: ["#00FF00", "#000000", "#FFFFFF"][i] || "#FFFFFF"}))];
        this.widgets.push({name:"preview_frame", value:0}, {name:"sampling_mode", value:"3x3 Average"});
        this.id = 7;
        this.size = [300, 100];
    }
    addDOMWidget(name, type, root, options) { this.root = root; const w = {name, type, options}; this.widgets.push(w); return w; }
    computeSize() { return [300, 100]; }
    setSize(size) { this.size = size; }
}
await extension.beforeRegisterNodeDef(Node, {name: "SkebaFixedPaletteQuantize"});
const node = new Node(); node.onNodeCreated();
const visible = n => n.root.children.slice(0,16).filter(row => row.style.display !== "none").length;
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

await node.root.children[16].events.click();
assert.deepEqual(Object.keys(queued.output).sort(), ["1","7"]);
assert.equal(queued.output["7"].class_type, "SkebaPaletteFramePreview");
node.onExecuted({palette_preview:[{token:"a".repeat(32),filename:"test.png",subfolder:"skeba_palette",type:"temp",frame:0,frames:4,width:9,height:5}]});
node.root.children[1].children[3].events.click();
assert.equal(node.root.children[1].children[3].textContent, "PICKING...");
await node.root.children[18].events.click({clientX:200,clientY:100});
assert.equal(node.widgets[2].value, "#0CE712");
assert.equal(node.root.children[1].children[1].value, "#0CE712");
assert.equal(sampled.u, 0.5); assert.equal(sampled.v, 0.5);
assert.equal(sampled.sampling_mode, "3x3 Average");
const pickedSave = JSON.parse(JSON.stringify(node.widgets.slice(0,19).map(w=>w.value)));
pickedSave.forEach((value,i)=>{restored.widgets[i].value=value;}); restored.onConfigure();
assert.equal(restored.root.children[1].children[2].value, "#0CE712");
node.widgets.find(w=>w.name==="preview_frame").callback();
assert.equal(node.root.children[18].style.display, "none");
console.log("Preview-only queue, original coordinate mapping, eyedropper and picked-color save/load passed");
