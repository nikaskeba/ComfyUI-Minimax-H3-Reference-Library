import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage(); await page.goto('http://127.0.0.1:8188');
 await page.waitForFunction(()=>window.comfyAPI?.app?.app?.graph && window.LiteGraph?.registered_node_types?.SkebaCustomChoice);
 const state=await page.evaluate(async()=>{
 const {app}=await import('/scripts/app.js');
 const n=window.LiteGraph.createNode('SkebaCustomChoice'); app.graph.add(n);
 const {subgraph,node:host}=app.graph.convertToSubgraph(new Set([n]));
 const inner=subgraph.nodes.find(x=>x.type==='SkebaCustomChoice');
 const input=subgraph.addInput('Selection','COMBO'); input.connect(inner.inputs.find(x=>x.name==='selected'),inner);
 const prompt=await app.graphToPrompt();
 const queued=Object.values(prompt.output).find(item=>item.class_type==='SkebaCustomChoice')?.inputs;
 const old=window.LiteGraph.createNode('SkebaCustomChoice'); app.graph.add(old);
 const migrated=app.graph.convertToSubgraph(new Set([old]));
 const oldInner=migrated.subgraph.nodes.find(x=>x.type==='SkebaCustomChoice');
 const oldSocket=oldInner.addInput('choices','STRING',{widget:{name:'choices'}});
 const legacyInput=migrated.subgraph.addInput('Choice list','STRING');
 legacyInput.connect(oldSocket,oldInner);
 await new Promise(resolve=>setTimeout(resolve,50));
 return {fresh:{innerInputs:inner.inputs.map(i=>i.name),hostInputs:host.inputs.map(i=>i.type),hostWidgets:host.widgets.map(w=>w.type),queued},legacy:{innerInputs:oldInner.inputs.map(i=>({name:i.name,linked:i.link!=null})),hostInputs:migrated.node.inputs.map(i=>i.type),hostWidgets:migrated.node.widgets.map(w=>w.type)}};
 });
 assert.deepEqual(state.fresh.innerInputs,['selected','output_type']);
 assert.deepEqual(state.fresh.hostInputs,['COMBO']);
 assert.ok(state.fresh.hostWidgets.includes('combo'));
 assert.equal(state.fresh.queued.choices,'5\n22\n39\n56');
 assert.equal(state.fresh.queued.selected,'22');
 assert.equal(state.legacy.innerInputs.some(i=>i.name==='choices'),false);
 assert.equal(state.legacy.innerInputs.find(i=>i.name==='selected')?.linked,true);
 assert.deepEqual(state.legacy.hostInputs,['COMBO']);
 assert.ok(state.legacy.hostWidgets.includes('combo'));
 console.log('Custom Choice subgraph: selected combo, queue serialization, and legacy choices promotion passed.');
} finally {await browser.close();}


