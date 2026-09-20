import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
let extension;
const app={registerExtension(value){extension=value;}};
const code=(await fs.readFile(new URL('../web/disk_video.js',import.meta.url),'utf8')).replace('import { app } from "../../scripts/app.js";','');
new Function('app',code)(app);
class Node {constructor(){this.properties={};this.widgets=[{name:'preview_clip',value:false},{name:'live_playlist',value:false}];}onSerialize(){this.originalSerialize=true;}onConfigure(){this.originalConfigure=true;}}
await extension.beforeRegisterNodeDef(Node,{name:'SkebaSaveClipToFile'});
for(const values of [[true,true],[true,false],[false,true],[false,false]]){
 const node=new Node();node.widgets.forEach((w,i)=>w.value=values[i]);const saved={properties:{other:'kept'}};node.onSerialize(saved);
 const restored=new Node();restored.widgets.reverse();restored.onConfigure(JSON.parse(JSON.stringify(saved)));
 assert.deepEqual(['preview_clip','live_playlist'].map(name=>restored.widgets.find(w=>w.name===name).value),values);
 assert.equal(saved.properties.other,'kept');assert.ok(node.originalSerialize&&restored.originalConfigure);
}
const legacy=new Node();legacy.widgets[0].value=true;legacy.onConfigure({properties:{}});assert.equal(legacy.widgets[0].value,true);
console.log('Clip toggle named persistence: all combinations, reordered widgets, legacy workflows passed');
