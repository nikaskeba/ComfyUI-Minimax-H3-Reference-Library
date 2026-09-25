import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage();
 await page.setContent('<main style="height:600px;width:620px"></main>');
 const source=await fs.readFile(new URL('../web/prompt_list_text.js',import.meta.url),'utf8');
 await page.evaluate(source=>{
  const app={registerExtension(ext){window.extension=ext;}};
  new Function('app',source.replace(/^import .*;\r?\n/gm,'').replace(/export function/g,'function'))(app);
  extension.setup();
  class Node {
   constructor(){this.widgets=[{name:'text',value:''}];}
   addDOMWidget(name,type,element){document.querySelector('main').append(element);}
   setSize(){}
  }
  extension.beforeRegisterNodeDef(Node,{name:'SkebaPromptListText'});
  window.node=new Node();node.onNodeCreated();
 },source);
 const text='[new_location] [s=15]\nsubject_definitions:\n{Jerry_BC} Wardrobe: blue shirt\n<location:room = A room.>\ndetailed_description:\nA <script>literal text</script>\ntimeline:\n[Shot 1] {Jerry_BC} says <d>[English §Jerry_BC§]Hi.</d>\noverall_soundscape:\nQuiet\nnon_diegetic_music:\nNone\n|\n[s=5]\ntimeline:\n[Shot 1] Exit. |';
 await page.locator('textarea').fill(text);
 await page.getByRole('tab',{name:'Formatted view'}).click();
 assert.equal(await page.locator('.skeba-prompt-card').count(),3);
 assert.equal(await page.locator('.skeba-prompt-break').textContent(),'New location');
 assert.match(await page.locator('.skeba-prompt-view').textContent(),/2 prompts/);
 assert.match(await page.locator('.skeba-prompt-view').textContent(),/A <script>literal text<\/script>/);
 assert.equal(await page.locator('.skeba-prompt-view script').count(),0);
 assert.equal(await page.evaluate(()=>node.widgets[0].value),text);
 await page.getByRole('tab',{name:'Raw text'}).click();assert.equal(await page.locator('textarea').inputValue(),text);
 await page.evaluate(()=>{node.widgets[0].value='Reloaded | second';node.onConfigure();});
 assert.equal(await page.locator('textarea').inputValue(),'Reloaded | second');
 console.log('Prompt text preservation, formatting, safe markup and widget restoration passed');
} finally {await browser.close();}
