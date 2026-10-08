import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage();await page.goto('about:blank');
 const code=await fs.readFile(new URL('../manager/voice-description.js',import.meta.url),'utf8');
 await page.evaluate(code=>{
  const factory=new Function(code.replaceAll('export ','')+'; return voiceDescriptionControl;')();
  window.field=document.createElement('textarea');field.value='Original';document.body.append(field);
  window.key='first';window.calls=0;
  window.control=factory(field,()=>key?{key,run:()=>{calls++;return new Promise((resolve,reject)=>{window.finish=resolve;window.fail=reject;});}}:null);
  document.body.append(control.element);
 },code);
 const generate=page.getByRole('button',{name:'Generate voice description'});
 await generate.click();assert.equal(await generate.isDisabled(),true);
 await page.evaluate(()=>{field.value='Manual edit';field.dispatchEvent(new Event('input'));finish({description:'Stale',seconds:15});});
 await page.waitForFunction(()=>!document.querySelector('button').disabled);
 assert.equal(await page.locator('textarea').inputValue(),'Manual edit');
 await generate.click();await page.evaluate(()=>{key='second';finish({description:'Wrong source',seconds:15});});
 await page.waitForFunction(()=>!document.querySelector('button').disabled);
 assert.equal(await page.locator('textarea').inputValue(),'Manual edit');
 await generate.click();await page.evaluate(()=>fail(new Error('Unreadable audio')));
 await page.waitForFunction(()=>!document.querySelector('button').disabled);
 assert.equal(await page.locator('textarea').inputValue(),'Manual edit');
 assert.match(await page.getByRole('status').textContent(),/Unreadable/);
 await generate.click();await page.evaluate(()=>finish({description:'<img src=x onerror=alert(1)>',seconds:3}));
 await page.getByRole('button',{name:'Undo',exact:true}).waitFor();
 assert.equal(await page.locator('img').count(),0);
 await page.getByRole('button',{name:'Undo',exact:true}).click();
 assert.equal(await page.locator('textarea').inputValue(),'Manual edit');
 await page.evaluate(()=>{key=null;control.refresh();});assert.equal(await generate.isDisabled(),true);
 console.log('Voice control: stale edits/sources, failure, Undo, literal text, availability and duplicate-click protection passed.');
} finally {await browser.close();}
