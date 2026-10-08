import assert from "node:assert/strict";
import fs from "node:fs/promises";
import {execFileSync} from "node:child_process";
import {createRequire} from "node:module";
const {chromium} = createRequire(import.meta.url)("playwright");
const schema = JSON.parse(execFileSync(new URL("../../../.venv/Scripts/python.exe", import.meta.url).pathname.replace(/^\/(\w:)/,"$1"), ["-c", "import compiler_templates,json; print(json.dumps(compiler_templates.SkebaH3CompilerTemplates.INPUT_TYPES()))"], {encoding:"utf8"}));
const code = await fs.readFile(new URL("../web/compiler_templates.js", import.meta.url), "utf8");
const previewCode = await fs.readFile(new URL("../web/compiler_template_preview.js", import.meta.url), "utf8");
const catalogCode = await fs.readFile(new URL("../manager/refmod-catalog.js", import.meta.url), "utf8");
const browser = await chromium.launch({headless:true, channel:"chrome"});
try {
 const page = await browser.newPage();
 await page.goto("about:blank");
 await page.evaluate(async ({code,schema,previewCode,catalogCode}) => {
  const app = {registerExtension(extension){window.extension=extension;}};
  const catalog = new Function(catalogCode.replaceAll("export function", "function") + ";return {groupCatalog,refmodTag};")();
  const api = {async fetchApi(path, options) {
   const json = data => new Response(JSON.stringify(data), {headers:{"content-type":"application/json"}});
   if(path.endsWith("compiler-template-preview")) {
    const request = JSON.parse(options.body);window.lastPreviewRequest=request;
    const values={audio:"<Audio 1>",subject:"<Subject 1>",speaker:" (S1)"};
    const template=JSON.parse(request.compiler_templates).templates.voice_reference;
    return json({examples:{voice_reference:[template.replace(/\[\[([a-z_]+)\]\]/g,(_,key)=>values[key])]},prompt:"Example compiled",voice_description:"Raspy voice.",has_audio:true});
   }
   if(path.includes("h3-refmods")) return json([{file:"library/Kryten.safetensors",member:0,kind:"video",subject_name:"Kryten",preview:true},{file:"library/Kryten.safetensors",member:1,kind:"audio"}]);
   if(path.includes("h3-built-in"))return json({records:[{tag:"Jerry",library_tag:"Jerry_BC",name:"Jerry",has_audio:true}]});
   return json({records:[{id:"alf",tag:"ALF",name:"ALF",has_audio:true}]});
  }};
  const createTemplatePreview = new Function("api","groupCatalog","refmodTag",previewCode.replace(/^import .*;\r?\n/gm,"").replace("export function", "function")+";return createTemplatePreview;")(api,catalog.groupCatalog,catalog.refmodTag);
  new Function("app", "createTemplatePreview", code.replace(/^import .*;\r?\n/gm,""))(app,createTemplatePreview);
  class Node {
   constructor(){this.widgets=Object.entries(schema.required).map(([name,[,opts]])=>({name,value:opts.default}));this.graph={setDirtyCanvas(){}};}
   setSize(size){this.size=size;}
   addDOMWidget(name,type,element,options){document.body.append(element);this.widgets.push({name,type,options});}
  }
  await extension.beforeRegisterNodeDef(Node,{name:"SkebaH3CompilerTemplates",input:schema});
  window.node = new Node();node.onNodeCreated();
 }, {code,schema,previewCode,catalogCode});
 assert.equal(await page.locator('select[aria-label="Template group"] option').count(),4);
 await page.getByLabel("Template group").selectOption("Voice definitions and dialogue bindings");
 const field=page.getByLabel("voice_reference",{exact:true});
 const text="[[audio]] guides [[subject]][[speaker]]. <img src=x onerror=alert(1)>";
 await field.fill(text);
 assert.equal(await page.evaluate(()=>node.widgets.find(w=>w.name==='voice_reference').value),text);
 await page.getByLabel("Template group").selectOption("Summary additions");
 await page.getByLabel("summary_task_prefix",{exact:true}).fill("");
 const saved=await page.evaluate(()=>node.widgets.slice(0,-1).map(w=>w.value));
 await page.evaluate(saved=>{node.widgets.slice(0,-1).forEach((w,i)=>w.value=saved[i]);node.onConfigure();},saved);
 assert.equal(await page.getByLabel("summary_task_prefix",{exact:true}).inputValue(),"");
 await page.getByLabel("Template group").selectOption("Voice definitions and dialogue bindings");
 assert.equal(await field.inputValue(),text);
 assert.equal(await page.locator("img").count(),0);
 await page.getByText("Reset to defaults",{exact:true}).click();
 assert.equal(await field.inputValue(),schema.required.voice_reference[1].default);
 await page.getByRole('button',{name:'Import template JSON'}).click();
 const importText=page.getByLabel('Template JSON to import');
 const originalRetention=await page.evaluate(()=>node.widgets.find(w=>w.name==='retention_voice_reference').value);
 await importText.fill('{"templates":{"voice_reference":"Changed", "not_a_field":"Bad"}}');
 await page.getByRole('button',{name:'Apply imported templates'}).click();
 assert.match(await page.getByRole('alert').textContent(),/Unknown template field/);
 assert.equal(await field.inputValue(),schema.required.voice_reference[1].default);
 await importText.fill('{"templates":{"voice_reference":"[[made_up]]"}}');
 await page.getByRole('button',{name:'Apply imported templates'}).click();
 assert.match(await page.getByRole('alert').textContent(),/invalid placeholder/);
 await importText.fill('{"version":2,"templates":{"voice_reference":"Bad"}}');
 await page.getByRole('button',{name:'Apply imported templates'}).click();
 assert.match(await page.getByRole('alert').textContent(),/version: 1/);
 await importText.fill('{"templates":');
 await page.getByRole('button',{name:'Apply imported templates'}).click();
 assert.match(await page.getByRole('alert').textContent(),/Invalid JSON/);
 await importText.fill('{"templates":{"voice_reference":"<b>[[audio]] guides [[identity]].</b>","summary_task_prefix":""}}');
 await page.getByRole('button',{name:'Apply imported templates'}).click();
 assert.equal(await field.inputValue(),'<b>[[audio]] guides [[identity]].</b>');
 assert.equal(await page.evaluate(()=>node.widgets.find(w=>w.name==='summary_task_prefix').value),'');
 assert.equal(await page.evaluate(()=>node.widgets.find(w=>w.name==='retention_voice_reference').value),originalRetention);
 assert.equal(await page.locator('b').count(),0);
 await page.getByRole('button',{name:'Import template JSON'}).click();
 await page.getByLabel('Choose template JSON file').setInputFiles({name:'voice.json',mimeType:'application/json',buffer:Buffer.from('{"version":1,"templates":{"retention_voice_reference":"[[audio]] follows [[identity]]: [[voice_description]]"}}')});
 await page.getByRole('button',{name:'Apply imported templates'}).click();
 assert.equal(await page.getByLabel('Template group').inputValue(),'Retention analysis');
 assert.equal(await page.getByLabel('retention_voice_reference',{exact:true}).inputValue(),'[[audio]] follows [[identity]]: [[voice_description]]');
 assert.equal(await page.evaluate(()=>node.widgets.find(w=>w.name==='voice_reference').value),'<b>[[audio]] guides [[identity]].</b>');
 const imported=await page.evaluate(()=>node.widgets.slice(0,-1).map(w=>w.value));
 await page.evaluate(values=>{node.widgets.slice(0,-1).forEach((w,i)=>w.value=values[i]);node.onConfigure();},imported);
 assert.equal(await page.getByLabel('retention_voice_reference',{exact:true}).inputValue(),'[[audio]] follows [[identity]]: [[voice_description]]');
 assert.equal(await page.evaluate(()=>node.widgets.at(-1).options.serialize),false);
 await page.getByLabel('Template group').selectOption('Voice definitions and dialogue bindings');
 await page.getByText("Preview with a reference",{exact:true}).click();
 await page.getByLabel("Preview reference",{exact:true}).selectOption("saved:alf");
 await page.getByRole("status").filter({hasText:"Example compiled"}).waitFor();
 assert.match(await page.getByLabel("voice_reference preview",{exact:true}).textContent(),/Audio 1/);
 await field.fill("[[subject]][[speaker]] uses [[audio]].");
 await page.waitForFunction(()=>document.querySelector('[aria-label="voice_reference preview"]').textContent==='<Subject 1> (S1) uses <Audio 1>.');
 await page.getByLabel("Search preview references").fill("{Kryten_rm}");
 await page.getByLabel("Preview reference",{exact:true}).selectOption("refmod:library/Kryten.safetensors");
 await page.waitForFunction(()=>window.lastPreviewRequest.tag==='Kryten_rm');
 assert.equal(await page.evaluate(()=>window.lastPreviewRequest.preview_voice),true);
 assert.equal(await page.evaluate(()=>node.properties.skeba_template_preview_reference),'refmod:library/Kryten.safetensors');
 await page.getByLabel("Search preview references").fill("Jerry");
 assert.match(await page.getByLabel("Preview reference",{exact:true}).textContent(),/Jerry_BC/);
 console.log("Template editor groups, editing, persistence, empty fields, reset and literal HTML passed.");
} finally {await browser.close();}
