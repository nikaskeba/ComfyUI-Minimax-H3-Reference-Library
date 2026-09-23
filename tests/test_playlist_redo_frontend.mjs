import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
let extension, node, submitted;
const alerts=[];
const app={registerExtension(value){extension=value;},async graphToPrompt(){
 return {output:{save:{class_type:'SkebaPlaylistRedoSave',inputs:{crf:node.widgets.find(w=>w.name==='crf').value}}}};
}};
const api={async fetchApi(path,options){submitted=JSON.parse(options.body);return {ok:true,json:async()=>({name:'Test'})};}};
const window={prompt:()=> 'Test',alert:message=>alerts.push(message)};
const code=(await fs.readFile(new URL('../web/playlist_redo.js',import.meta.url),'utf8')).replace(/^import .*;\r?\n/gm,'');
new Function('app','api','window',code)(app,api,window);
class Node {
 constructor(){this.comfyClass='SkebaPlaylistRedoSave';this.widgets=[{name:'crf',value:18}];}
 addWidget(type,name,value,callback,options){this.widgets.push({type,name,value,callback,options});}
 onSerialize(){this.serialized=true;}
 onConfigure(data){this.configured=true;this.widgets.forEach((w,i)=>w.value=data.widgets_values?.[i]);}
}
await extension.beforeRegisterNodeDef(Node,{name:'SkebaPlaylistRedoSave'});
for(const value of [0,18,27,51]){
 node=new Node();await extension.nodeCreated(node);
 node.widgets.find(w=>w.name==='crf').value=value;
 const data={widgets_values:[value,null]};node.onSerialize(data);
 assert.equal(data.properties.skeba_redo_crf,value);
 node=new Node();await extension.nodeCreated(node);node.widgets.reverse();
 node.onConfigure(JSON.parse(JSON.stringify(data)));
 assert.equal(node.widgets.find(w=>w.name==='crf').value,value);
 assert.ok(node.configured);
 await node.widgets.find(w=>w.type==='button').callback();
 assert.equal(submitted.graph.save.inputs.crf,value);
 assert.equal(node.widgets.find(w=>w.type==='button').options.serialize,false);
}
for(const [data,expected] of [
 [{},18], [{widgets_values:[null]},18], [{widgets_values:[null,27]},27],
 [{widgets_values:[0,null]},0], [{widgets_values:[18],properties:{skeba_redo_crf:0}},0],
 [{widgets_values:[null],widgets_values_named:{crf:25}},25],
]){
 node=new Node();await extension.nodeCreated(node);node.onConfigure(data);
 assert.equal(node.widgets.find(w=>w.name==='crf').value,expected);
 await node.widgets.find(w=>w.type==='button').callback();
 assert.equal(submitted.graph.save.inputs.crf,expected);
}
assert.ok(alerts.every(message=>message.startsWith('Saved Test')));
console.log('Redo CRF named persistence, legacy layouts, defaults and registration exports passed');

app.graph={setDirtyCanvas(){}};
node=new Node();node.id=930;node.comfyClass='SkebaPlaylistWorkflow';node.properties={};
api.fetchApi=async(path,options)=>{submitted=JSON.parse(options.body);return {ok:true,json:async()=>({id:'a'.repeat(32),name:'Main'})};};
await extension.nodeCreated(node);
await node.widgets.find(w=>w.type==='button').callback();
assert.equal(submitted.registration_id,'930');assert.equal(submitted.template_id,undefined);
assert.equal(node.properties.skeba_playlist_template,'a'.repeat(32));
await node.widgets.find(w=>w.type==='button').callback();assert.equal(submitted.template_id,'a'.repeat(32));
console.log('Shared main workflow registration and stable template updates passed');
