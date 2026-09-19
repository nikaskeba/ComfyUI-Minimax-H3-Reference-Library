import assert from "node:assert/strict";
import fs from "node:fs";

class Element {
    constructor(tag) { this.tag=tag; this.children=[]; this.style={}; this.events={}; this.value=""; this.hidden=false; }
    append(...items) { this.children.push(...items); }
    prepend(...items) { this.children.unshift(...items); }
    before(item) { this.beforeItem=item; }
    add(item) { this.append(item); }
    replaceChildren(...items) { this.children=items; }
    setAttribute() {}
    addEventListener(name,fn) { this.events[name]=fn; }
    dispatchEvent(event) { this["on"+event.type]?.(event); this.events[event.type]?.(event); }
}
const document={createElement:tag=>new Element(tag)};
function Option(text,value) { return {textContent:text,value}; }
const catalog=[{file:"appearance.safetensors",member:null,kind:"image",name:"Face",token_count:4}, {file:"voices.safetensors",member:0,kind:"audio",name:"Voice",token_count:400}];
const fetch=async()=>({ok:true,text:async()=>JSON.stringify(catalog)});
const source=fs.readFileSync(new URL("../manager/refmod-picker.js",import.meta.url),"utf8").replaceAll("export async function","async function");
const fields=new Function("document","Option","fetch",source+"\nreturn refmodFields;")(document,Option,fetch);
const record={appearance_source:"refmod",appearance_refmod:{file:"appearance.safetensors",member:null},voice_source:"media",voice_refmod:{file:"voices.safetensors",member:0}};
const editor=await fields(record);
const standard=new Element("div"); editor.addTabs(standard);
assert.equal(standard.hidden,true);
assert.equal(editor.read().appearance_source,"refmod");
assert.equal(editor.read().voice_source,"media");
const tabs=editor.element.beforeItem;
tabs.children[0].onclick();
assert.equal(editor.element.hidden,true);
assert.equal(editor.read().appearance_source,"media");
assert.deepEqual(editor.read().appearance_refmod,record.appearance_refmod);
assert.deepEqual(editor.read().voice_refmod,record.voice_refmod);
tabs.children[1].onclick();
assert.equal(standard.hidden,true);
assert.equal(editor.read().appearance_source,"refmod");
assert.equal(editor.read().voice_source,"refmod");
const fresh=await fields({}); fresh.addTabs(new Element("div"));
assert.equal(fresh.read().appearance_source,"media");
fresh.element.beforeItem.children[1].onclick();
assert.equal(fresh.read().appearance_source,"refmod");
assert.equal(fresh.read().appearance_refmod,null);
console.log("RefMod picker source switching and attachment preservation passed");
