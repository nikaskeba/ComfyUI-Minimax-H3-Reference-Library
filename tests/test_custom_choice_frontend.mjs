import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage();
 await page.goto('about:blank');
 const code=await fs.readFile(new URL('../web/custom_choice.js',import.meta.url),'utf8');
 await page.evaluate(async code=>{
  const app={registerExtension(ext){window.ext=ext;}};
  new Function('app',code.replace(/^import .*;\r?\n/gm,'').replace('export function','function'))(app);
  class Node {
   constructor(){this.widgets=[{name:'choices',value:'5\n22\n39\n56'},{name:'selected',value:'22'},{name:'output_type',value:'text'}];this.graph={setDirtyCanvas(){}};}
   setSize(size){this.size=size;}
   addDOMWidget(name,type,element,options){document.body.append(element);this.widgets.push({name,type,options});}
  }
  await window.ext.beforeRegisterNodeDef(Node,{name:'SkebaCustomChoice'});
  window.node=new Node();window.node.onNodeCreated();
 },code);
 const select=page.getByLabel('Selected choice');
 assert.equal(await select.inputValue(),'22');
 await select.selectOption('39');
 assert.equal(await page.evaluate(()=>node.widgets[1].value),'39');
 await page.getByText('Edit choices',{exact:true}).click();
 await page.getByLabel('Custom choices').fill('standard\npre-cut reinforcement\nscene reference');
 await page.getByText('Apply choices',{exact:true}).click();
 await select.selectOption('scene reference');
 const saved=await page.evaluate(()=>node.widgets.slice(0,3).map(w=>w.value));
 assert.equal(saved[1],'scene reference');
 await page.evaluate(saved=>{node.widgets.slice(0,3).forEach((w,i)=>w.value=saved[i]);node.onConfigure();},saved);
 assert.equal(await select.inputValue(),'scene reference');
 await page.getByText('Edit choices',{exact:true}).click();
 await page.getByLabel('Custom choices').fill('');
 await page.getByText('Apply choices',{exact:true}).click();
 assert.equal(await page.getByRole('alert').textContent(),'Add at least one choice.');
 assert.deepEqual(await page.evaluate(()=>node.widgets.slice(0,3).map(w=>w.value)),saved);
 await page.getByText('Cancel',{exact:true}).click();
 await page.getByText('Edit choices',{exact:true}).click();
 await page.getByLabel('Custom choices').fill('<img src=x onerror=alert(1)>');
 await page.getByText('Apply choices',{exact:true}).click();
 assert.equal(await page.locator('img').count(),0);
 assert.equal(await select.inputValue(),'<img src=x onerror=alert(1)>');
 assert.equal(await page.evaluate(()=>node.widgets[3].options.serialize),false);
 console.log('Custom-choice UI: selection, editing, restoration, cancel, empty validation, and literal HTML passed.');
} finally {await browser.close();}
