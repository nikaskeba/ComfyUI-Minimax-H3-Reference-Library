import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage(); await page.goto('http://127.0.0.1:8188');
 await page.waitForFunction(()=>window.comfyAPI?.app?.app?.graph && window.LiteGraph?.registered_node_types?.SkebaCustomChoice);
 console.log(await page.evaluate(async()=>{
 const {app}=await import('/scripts/app.js');
 const n=window.LiteGraph.createNode('SkebaCustomChoice'); app.graph.add(n);
 const {subgraph,node:host}=app.graph.convertToSubgraph(new Set([n]));
 const inner=subgraph.nodes.find(x=>x.type==='SkebaCustomChoice');
 const input=subgraph.addInput('Selection','COMBO'); input.connect(inner.inputs.find(x=>x.name==='selected'),inner);
 return {widgets:host.widgets.map(w=>({name:w.name,type:w.type,cls:w.constructor.name,options:w.options})),inner:inner.widgets.map(w=>({name:w.name,type:w.type,cls:w.constructor.name})),inputs:host.inputs.map(i=>({name:i.name,type:i.type,widget:i.widget})),data:host.serialize()};
 }));
} finally {await browser.close();}


