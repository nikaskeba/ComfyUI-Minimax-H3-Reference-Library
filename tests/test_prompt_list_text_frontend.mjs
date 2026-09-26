import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage();
 const errors=[];page.on("pageerror", error=>errors.push(error.message));
 await page.route("http://prompt.test/", route=>route.fulfill({contentType:"text/html",body:"<html></html>"}));
 await page.goto("http://prompt.test/");
 await page.setContent('<main style="height:600px;width:620px"></main>');
 const source=(await fs.readFile(new URL('../web/prompt_rich_text.js',import.meta.url),'utf8'))+'\n'+await fs.readFile(new URL('../web/prompt_list_text.js',import.meta.url),'utf8');
 await page.evaluate(source=>{
  const app={registerExtension(ext){window.extension=ext;}};
  const api={fetchApi:async path=>({ok:true,json:async()=>({records:path.includes('built-in')?[{tag:'Elaine',library_tag:'Elaine_BC'}]:[{id:'room',tag:'Apartment',reference_type:'location'},{id:'george',tag:'George',reference_type:'character'}]})})};
  new Function('app','api',source.replace(/^import .*;\r?\n/gm,'').replace(/export function/g,'function'))(app,api);
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

 assert.equal(await page.locator('.skeba-prompt-block').count(),3);
 assert.equal(await page.locator('.skeba-prompt-break').textContent(),'Scene change');
 assert.equal(await page.locator('.skeba-inline-dialogue').count(),1);
 assert.equal(await page.getByRole('textbox',{name:'Dialogue speech',exact:true}).inputValue(),'Hi.');
 assert.equal(await page.locator('.skeba-prompt-view script').count(),0);
 assert.equal(await page.evaluate(()=>node.widgets[0].value),text);
 await page.getByRole('tab',{name:'Raw text'}).click();assert.equal(await page.getByRole('textbox',{name:'Prompt list separated by vertical bars'}).inputValue(),text);
 await page.getByRole('tab',{name:'Formatted view'}).click();
 await page.getByLabel('Length (seconds)').fill('0');await page.getByLabel('Length (seconds)').blur();
 assert.equal(await page.evaluate(()=>node.widgets[0].value),text);
 assert.match(await page.locator('[role=status]').first().textContent(),/positive duration/);
 await page.getByLabel('Length (seconds)').fill('7.5');await page.getByLabel('Length (seconds)').blur();
 assert.equal(await page.evaluate(()=>node.widgets[0].value),text.replace('[s=15]','[s=7.5]'));
 await page.getByRole('button',{name:'Undo',exact:true}).click();assert.equal(await page.evaluate(()=>node.widgets[0].value),text);
 await page.getByRole('button',{name:'Redo',exact:true}).click();assert.match(await page.evaluate(()=>node.widgets[0].value),/s=7.5/);
 await page.getByLabel('Scene change').uncheck();assert.ok(!(await page.evaluate(()=>node.widgets[0].value)).includes('[new_location]'));
 await page.getByRole('textbox',{name:'Dialogue speech',exact:true}).fill('Bonjour!');
 await page.getByLabel('Dialogue language',{exact:true}).fill('French');
 await page.getByLabel('Dialogue speaker',{exact:true}).fill('<voice:guest>');
 assert.match(await page.evaluate(()=>node.widgets[0].value),/<d>\[French <voice:guest>\]Bonjour!<\/d>/);
 assert.ok((await page.evaluate(()=>node.widgets[0].value)).endsWith(text.split('|').slice(1).join('|')));
 await page.getByRole('textbox',{name:'Description text',exact:true}).fill('New description <img src=x onerror=alert(1)>');
 assert.equal(await page.locator('.skeba-prompt-view img').count(),0);
 await page.getByRole('button',{name:'Insert prompt at position 2',exact:true}).click();
 assert.equal(await page.locator('.skeba-prompt-block').count(),4);
 assert.equal(await page.getByLabel('Length (seconds)').inputValue(),'15');
 assert.equal(await page.getByLabel('Scene change').isChecked(),false);
 await page.getByRole('button',{name:'Undo',exact:true}).click();assert.equal(await page.locator('.skeba-prompt-block').count(),3);
 await page.evaluate(()=>{node.widgets[0].value='Opening text\r\ntimeline:\r\n<d>[English]Hello.</d> text <d>broken | second ||';node.onConfigure();});
 const restored=await page.evaluate(()=>node.widgets[0].value);
 assert.equal(await page.getByLabel('Length (seconds)').inputValue(),'15');
 assert.match(await page.locator('.skeba-prompt-block').first().textContent(),/default/);
 assert.match(await page.locator('.skeba-prompt-view').textContent(),/Unrecognized dialogue/);
 assert.equal(await page.getByLabel('Dialogue speaker',{exact:true}).inputValue(),'');
 await page.getByRole('tab',{name:'Raw text'}).click();
 assert.equal(await page.getByRole('textbox',{name:'Prompt list separated by vertical bars'}).inputValue(),restored.replaceAll('\r\n','\n'));
 assert.equal(await page.evaluate(()=>node.widgets[0].value),restored);
 await page.getByRole('tab',{name:'Formatted view'}).click();
 for(const position of [1,6]){
  await page.getByRole('button',{name:`Insert prompt at position ${position}`,exact:true}).click();
 }
 assert.equal(await page.locator('.skeba-prompt-block').count(),6);
 await page.evaluate(()=>{node.widgets[0].value='[s=12]\nsummary:\nOld summary\nretention_analysis:\nPreserved\ntimeline:\n<d>[French §A§]Bonjour.</d> then <d>[English <voice:b>]Hello.</d>\ncustom_section:\nKeep me';node.onConfigure();});
 assert.equal(await page.locator('.skeba-inline-dialogue').count(),2);
 await page.getByLabel('Dialogue speech',{exact:true}).nth(1).fill('Goodbye.');
 assert.match(await page.evaluate(()=>node.widgets[0].value),/custom_section:\nKeep me$/);
 assert.match(await page.evaluate(()=>node.widgets[0].value),/<d>\[French §A§\]Bonjour.<\/d>/);
 await page.getByRole('button',{name:'Undo',exact:true}).click();
 assert.equal(await page.getByLabel('Dialogue speech',{exact:true}).nth(1).inputValue(),'Hello.');
 await page.evaluate(text=>{node.widgets[0].value=text;node.onConfigure();},text);
 await page.screenshot({path:process.env.TEMP+'/skeba-prompt-visual-editor.png'});
 await page.evaluate(()=>{node.widgets[0].value=Array.from({length:80},(_,i)=>`[s=15]\ntimeline:\n[Shot 1] Prompt ${i}`).join('|');node.onConfigure();});
 assert.equal(await page.locator('.skeba-prompt-block').count(),80);
 assert.ok(await page.locator('.skeba-prompt-timeline').evaluate(e=>e.scrollWidth>e.clientWidth));
 await page.locator('.skeba-prompt-block').last().click();
 assert.match(await page.locator('.skeba-prompt-muted').first().textContent(),/Prompt 80 of 80/);
 // One timeline textbox, inline shot/reference highlighting, and no empty opening editor.
 await page.evaluate(()=>{node.widgets[0].value='[s=15]\n\nsubject_definitions:\n{Jerry_BC}\ntimeline:\n[Shot 1] {Jerry_BC} waits. <d>[English §Jerry_BC§]Hi.</d>';node.onConfigure();});
 const timelineField=page.getByRole('textbox',{name:'Timeline text',exact:true});
 assert.equal(await timelineField.count(),1);
 assert.equal(await page.getByRole('textbox',{name:'Opening / definitions text',exact:true}).count(),0);
 assert.equal(await timelineField.locator('.skeba-shot').count(),1);
 assert.equal(await timelineField.locator('.skeba-reference-token').count(),1);
 const timelinePanel=page.locator('.skeba-prompt-section').filter({has:timelineField});
 await timelinePanel.getByRole('button',{name:'Add shot',exact:true}).click();
 assert.match(await page.evaluate(()=>node.widgets[0].value),/\[Shot 2\]/);
 await timelinePanel.getByRole('button',{name:'Add dialogue',exact:true}).click();
 assert.equal(await timelineField.locator('.skeba-inline-dialogue').count(),2);
 await timelineField.getByLabel('Dialogue speech').last().fill('New speech.');
 assert.match(await page.evaluate(()=>node.widgets[0].value),/<d>\[English\]New speech.<\/d>/);
 await timelineField.getByRole('button',{name:'Remove dialogue',exact:true}).last().click();
 assert.ok(!(await page.evaluate(()=>node.widgets[0].value)).includes('New speech.'));
 await timelineField.getByRole('button',{name:'Remove shot marker',exact:true}).last().click();
 assert.ok(!(await page.evaluate(()=>node.widgets[0].value)).includes('[Shot 2]'));
 await timelinePanel.getByRole('button',{name:'Add reference',exact:true}).click();
 const picker=page.getByRole('dialog',{name:'Insert reference'});
 await picker.getByRole('textbox',{name:'Search references'}).fill('Elaine');
 await picker.getByRole('button',{name:'Insert {Elaine_BC}',exact:true}).click();
 assert.match(await page.evaluate(()=>node.widgets[0].value),/\{Elaine_BC\}/);
 await timelinePanel.getByRole('button',{name:'Add reference',exact:true}).click();
 await picker.getByRole('combobox',{name:'Reference type'}).selectOption('location');
 await picker.getByRole('button',{name:'Insert {Apartment}',exact:true}).click();
 assert.match(await page.evaluate(()=>node.widgets[0].value),/\{Apartment\}/);
 // Insert at a saved caret in the middle, not at the start/end after the popup takes focus.
 await page.evaluate(()=>{node.widgets[0].value='timeline:\nBefore. After.';node.onConfigure();const ed=document.querySelector('[aria-label="Timeline text"]');ed.focus();const text=ed.firstChild;const r=document.createRange();r.setStart(text,9);r.collapse(true);getSelection().removeAllRanges();getSelection().addRange(r);ed.dispatchEvent(new MouseEvent('mouseup'));});
 const middlePanel=page.locator('.skeba-prompt-section').filter({has:page.getByRole('textbox',{name:'Timeline text',exact:true})});
 await middlePanel.getByRole('button',{name:'Add reference',exact:true}).click();
 await page.getByRole('dialog',{name:'Insert reference'}).getByRole('button',{name:'Insert {Apartment}',exact:true}).click();
 assert.equal(await page.evaluate(()=>node.widgets[0].value),'timeline:\nBefore. {Apartment}After.');
 await page.getByRole('button',{name:'Undo',exact:true}).click();
 assert.equal(await page.evaluate(()=>node.widgets[0].value),'timeline:\nBefore. After.');
 await page.evaluate(()=>{node.widgets[0].value='[s=15]\n\nsubject_definitions:\n{Jerry_BC}\ntimeline:\n[Shot 1] {Jerry_BC} waits. <d>[English §Jerry_BC§]Hi.</d>';node.onConfigure();document.querySelector('.skeba-prompt-view').scrollTop=0;});
 await page.screenshot({path:process.env.TEMP+'/skeba-prompt-inline-editor.png'});
 for(const blank of ['', '  \r\n ']){
  await page.evaluate(value=>{node.widgets[0].value=value;node.onConfigure();},blank);
  assert.equal(await page.locator('.skeba-prompt-block').count(),0);
  assert.equal(await page.getByRole('textbox',{name:'Timeline text',exact:true}).count(),0);
  assert.equal(await page.evaluate(()=>node.widgets[0].value),blank);
  await page.getByRole('button',{name:'Add first scene',exact:true}).click();
  assert.equal(await page.locator('.skeba-prompt-block').count(),1);
  assert.equal(await page.getByLabel('Length (seconds)').inputValue(),'15');
  assert.equal(await page.getByRole('textbox',{name:'Timeline text',exact:true}).count(),1);
  assert.equal((await page.evaluate(()=>node.widgets[0].value)).includes('|'),false);
  await page.getByRole('button',{name:'Undo',exact:true}).click();
  assert.equal(await page.evaluate(()=>node.widgets[0].value),blank);
  await page.getByRole('button',{name:'Add first scene',exact:true}).waitFor();
  await page.getByRole('button',{name:'Redo',exact:true}).click();
  assert.equal(await page.locator('.skeba-prompt-block').count(),1);
 }
 await page.evaluate(()=>{node.widgets[0].value='[s=15]\n\nsubject_definitions:\n{Conan_BC}\n\ndetailed_description:\nA street.\n\ntimeline:\n[Shot 1] Waits.';node.onConfigure();});
 await page.getByRole('textbox',{name:'subject_definitions: text',exact:true}).fill('{Conan_BC} wearing a clown costume.');
 await page.getByRole('textbox',{name:'Description text',exact:true}).fill('Realistic render');
 await page.getByRole('tab',{name:'Raw text'}).click();
 const spaced=await page.getByRole('textbox',{name:'Prompt list separated by vertical bars'}).inputValue();
 assert.match(spaced,/subject_definitions:\n\{Conan_BC\} wearing a clown costume\.\n\ndetailed_description:\nRealistic render\n\ntimeline:\n/);
 await page.getByRole('tab',{name:'Formatted view'}).click();
 assert.equal(await page.getByRole('textbox',{name:'Description text',exact:true}).count(),1);
 assert.deepEqual(errors,[]);
 console.log('Visual prompt timeline, editing, insertion, undo/redo, exact text and restoration passed');
} finally {await browser.close();}
