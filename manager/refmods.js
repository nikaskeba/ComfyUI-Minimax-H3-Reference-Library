import {renderReferenceGuide,referenceGuideText} from "./reference-guide.js?v=1";
import {openVideoEditor} from "./video-selector.js?v=7";
import {groupCatalog,refmodTag,refmodGuideRecord} from "./refmod-catalog.js?v=2";
const $ = id => document.getElementById(id);
const fields=["reference_type","collection","name","file","subject_name","appearance","voice_description","description","frames","mode","resolution","grid","steps","video_seconds","audio_seconds"];
const selected=new Set(JSON.parse(localStorage.getItem("skeba-refmod-selection")||"[]"));
const numeric=new Set(["resolution","grid","steps","video_seconds","audio_seconds"]);
let sources=[],existing=null,companion=null,catalog=[],groups=[],folder="",uploading=0,busy=false,frameRows=[],storedVoice=null,keepVoice=true,previewData={frames:[],audio:null},baseline="";
const status=(message,error=false)=>{$("status").textContent=message;$("status").className=error?"error":"";};
async function request(url,options={}){const response=await fetch(url,options),text=await response.text();let result;try{result=JSON.parse(text);}catch{throw new Error(`${url} returned ${response.status} with a non-JSON response. Restart ComfyUI after updating the nodes, then refresh this page.`);}if(!response.ok)throw new Error(typeof result.error==="string"?result.error:JSON.stringify(result));return result;}
const selection=row=>({file:row.file,member:row.member??null});
const previewURL=row=>`/api/h3-refmods/preview?file=${encodeURIComponent(row.file)}&member=${row.member??""}`;
const mediaURL=data=>"/view?"+new URLSearchParams(data);
function button(label,action){const el=document.createElement("button");el.type="button";el.textContent=({Up:"↑",Down:"↓",Remove:"✕",Restore:"↶"})[label]||label;el.title=label;el.setAttribute("aria-label",label);el.onclick=action;return el;}
function values(){return Object.fromEntries(fields.map(id=>[id,numeric.has(id)?Number($(id).value):$(id).value]));}
function spec(){const data=values();const stem=data.name.trim().replace(/[<>:"/\\|?*\x00-\x1f]/g,"_").replace(/[. ]+$/g,"")||"reference";const folder=existing?.file.includes("/")?existing.file.slice(0,existing.file.lastIndexOf("/")+1):"library/";data.file=existing&&!$("overwrite").checked?existing.file:folder+stem+($("overwrite").checked?"_copy":"")+".safetensors";return {...data,video_frames:Math.max(1,Math.floor(data.video_seconds*24)),appearance_action:"append",audio_action:storedVoice&&keepVoice?"append":sources.some(s=>s.kind==="audio"||(s.kind==="video"&&s.include_audio))?"replace":"remove",keep_voice:keepVoice,limit_total_voice:true,sources,existing,companion,overwrite:Boolean(existing)&&!$("overwrite").checked,retrain:$("retrain").checked,frame_order:existing?frameRows.filter(row=>row.keep).map(row=>row.index):null};}
function snapshot(){return JSON.stringify(spec());}
function remember(){localStorage.setItem("skeba-refmod-draft",JSON.stringify({...spec(),frameRows,storedVoice,previewData}));summary();}
function summary(){const kept=frameRows.filter(row=>row.keep).length;$("edit-summary").textContent=`${kept} kept frames · ${sources.length} new sources${storedVoice&&keepVoice?" · stored voice":""}`;const unchanged=existing&&baseline===snapshot();$("save").disabled=busy||uploading>0||Boolean(unchanged);$("save").textContent=unchanged?"No changes":existing&&!sources.length&&!$("retrain").checked?"Save changes":"Train / Encode & Save";}
function showView(editor){$("cancel-edit").hidden=!existing;$("library-view").hidden=editor;$("edit-view").hidden=!editor;$("show-library").classList.toggle("active",!editor);$("show-editor").classList.toggle("active",editor);}
function modeChanged(){document.querySelectorAll(".compressed").forEach(el=>el.hidden=$("mode").value!=="training");$("retrain-row").hidden=!existing||!frameRows.length||$("mode").value!=="training";if($("retrain-row").hidden)$("retrain").checked=false;}
function syncFrames(){$("frames").value=frameRows.filter(row=>row.keep).map(row=>row.index).join(",");}
function move(list,index,offset){const next=index+offset;if(next>=0&&next<list.length)[list[index],list[next]]=[list[next],list[index]];}
function renderStored(){
 $("stored-frames").replaceChildren();$("stored-audio").replaceChildren();$("stored").hidden=!existing;
 frameRows.forEach((item,index)=>{
  const row=document.createElement("div");row.className="stored-row"+(item.keep?"":" omitted");row.draggable=true;row.dataset.index=index;
  row.ondragstart=event=>event.dataTransfer.setData("application/x-skeba-frame",String(index));row.ondragover=event=>{if([...event.dataTransfer.types].includes("application/x-skeba-frame"))event.preventDefault();};row.ondrop=event=>{const value=event.dataTransfer.getData("application/x-skeba-frame");if(!value)return;event.preventDefault();const from=Number(value);const [moved]=frameRows.splice(from,1);frameRows.splice(index,0,moved);syncFrames();renderStored();remember();};
  const keep=document.createElement("input");keep.type="checkbox";keep.checked=item.keep;keep.setAttribute("aria-label",`Keep frame ${item.index+1}`);keep.onchange=()=>{item.keep=keep.checked;syncFrames();renderStored();remember();};
  const box=document.createElement("div"),data=previewData.frames?.[item.index];
  const preview=document.createElement(data?"img":"div");preview.className="frame-preview"+(data?"":" frame-placeholder");if(data){preview.src=mediaURL(data);preview.alt=`Stored frame ${item.index+1}`;}else preview.textContent=`Frame ${item.index+1}
Preview not generated`;
  const badge=document.createElement("span");badge.className="stored-tag";badge.textContent="STORED";box.append(preview,badge);
  const body=document.createElement("div"),title=document.createElement("div"),meta=document.createElement("p"),controls=document.createElement("div");title.className="source-title";title.textContent=`Frame ${item.index+1}`;meta.className="frame-meta";meta.textContent=item.keep?"Kept exactly as stored · 1 latent frame":"Omitted from saved copy";controls.className="source-controls";
  controls.append(button("Up",()=>{move(frameRows,index,-1);syncFrames();renderStored();remember();}),button("Down",()=>{move(frameRows,index,1);syncFrames();renderStored();remember();}),button(item.keep?"Remove":"Restore",()=>{item.keep=!item.keep;syncFrames();renderStored();remember();}));body.append(title,meta,controls);row.append(keep,box,body);$("stored-frames").append(row);
 });
 if(storedVoice){const row=document.createElement("div");row.className="stored-row stored-voice";const keep=document.createElement("input");keep.type="checkbox";keep.checked=keepVoice;keep.setAttribute("aria-label","Keep stored voice");keep.onchange=()=>{keepVoice=keep.checked;renderStored();remember();};const body=document.createElement("div"),title=document.createElement("div"),info=document.createElement("p");title.className="source-title";title.textContent="Stored voice";info.className="frame-meta";info.textContent=`${((storedVoice.latent_t||0)/40).toFixed(2)} seconds · ${storedVoice.token_count??(storedVoice.latent_t||0)*2} tokens`;body.append(title,info);if(previewData.audio){const audio=document.createElement("audio");audio.controls=true;audio.preload="none";audio.src=mediaURL(previewData.audio);body.append(audio);}else{const note=document.createElement("p");note.className="muted";note.textContent="Generate previews to listen to the stored voice.";body.append(note);}body.append(button(keepVoice?"Remove":"Restore",()=>{keepVoice=!keepVoice;renderStored();remember();}));row.classList.toggle("omitted",!keepVoice);row.append(keep,body);$("stored-audio").append(row);}
}
function renderSources(){
 $("sources").replaceChildren();
 sources.forEach((source,index)=>{const row=document.createElement("div");row.className="source-row";const preview=document.createElement(source.kind==="image"?"img":source.kind==="video"?"video":"audio");preview.src=`/api/h3-refmods/sources/${encodeURIComponent(source.file)}`;preview.alt=source.name;if(source.kind!=="image"){preview.controls=true;preview.preload="metadata";}
 const body=document.createElement("div"),title=document.createElement("div"),controls=document.createElement("div");title.className="source-title";title.textContent=`${source.name} · new ${source.kind}`;controls.className="source-controls";
 controls.append(button("Up",()=>{move(sources,index,-1);renderSources();remember();}),button("Down",()=>{move(sources,index,1);renderSources();remember();}),button("Remove",()=>{sources.splice(index,1);renderSources();remember();}));
 if(source.kind==="video")controls.append(button(`Edit sections (${source.sections?.length||1})`,()=>openVideoEditor(source,sections=>{source.sections=sections;renderSources();remember();})));
 if(source.kind==="video"){const label=document.createElement("label"),check=document.createElement("input");check.type="checkbox";check.checked=Boolean(source.include_audio);label.className="include-voice";check.style.width="auto";check.onchange=()=>{source.include_audio=check.checked;remember();};label.append(check,document.createTextNode(" Include Voice"));controls.append(label);}
 if(source.kind!=="image"&&!source.sections?.length)for(const key of ["start","end"]){const label=document.createElement("label");label.textContent=key;const input=document.createElement("input");input.type="number";input.min="0";input.step="any";input.value=source[key]||0;input.oninput=()=>{source[key]=Number(input.value);remember();};label.append(input);controls.append(label);}body.append(title,controls);row.append(preview,body);$("sources").append(row);});
}
async function upload(files){if(busy)return;uploading++;summary();try{for(const file of files){status(`Uploading ${file.name}...`);const data=new FormData();data.append("file",file);const source=await request("/api/h3-refmods/sources",{method:"POST",body:data});sources.push({...source,start:0,end:0,include_audio:source.kind==="video"});renderSources();remember();}status("Sources ready.");}catch(error){status(error.message,true);}finally{uploading--;summary();$("upload").value="";}}
function chip(text,kind="neutral"){const el=document.createElement("span");el.className="chip "+kind;el.textContent=text;return el;}
function renderFolders(){const names=[...new Set(groups.map(group=>group.folder))].sort();$("folders").replaceChildren();for(const name of ["",...names]){const control=button(name||"All RefMods",()=>{folder=name;renderFolders();renderCatalog();});control.classList.toggle("active",folder===name);$("folders").append(control);}}
function renderCatalog(){
 $("assets").replaceChildren();const query=$("search").value.toLowerCase(),kind=$("kind-filter").value;
 const shown=groups.filter(group=>(!$("type-filter").value||(group.primary.reference_type||"character")===$("type-filter").value)&&(!$("collection-filter").value||group.primary.collection===$("collection-filter").value)&&(!folder||group.folder===folder)&&(!kind||(kind==="paired"?group.visual&&group.audio:kind==="visual"?group.visual:group.audio))&&`${group.name} ${group.files.join(" ")} ${group.rows.map(row=>row.description||"").join(" ")}`.toLowerCase().includes(query));
 for(const group of shown){const card=document.createElement("article");card.className="asset";const thumb=group.rows.find(row=>row.preview),preview=document.createElement(thumb?"img":"div");preview.className="asset-preview"+(thumb?"":" asset-placeholder");if(thumb){preview.src=previewURL(thumb);preview.alt=group.name;preview.loading="lazy";}else preview.textContent=group.audio&&!group.visual?"Audio":"RefMod";
 const body=document.createElement("div"),name=document.createElement("div"),badges=document.createElement("div"),files=document.createElement("div"),actions=document.createElement("div"),details=document.createElement("details");body.className="asset-body";name.className="asset-name";name.textContent=group.name;badges.className="badges";files.className="asset-files";files.textContent=group.files.join(" + ");actions.className="asset-actions";
 if(group.visual){const v=group.visual;badges.append(chip(`${v.kind} · ${Number(v.token_count).toLocaleString()} tokens`,"visual"),chip(`${v.mode==="encode"?"full":"compressed"} · ${v.latent_t??"?"} frames · ${v.latent_h??"?"}×${v.latent_w??"?"}`));}
 if(group.audio){const a=group.audio;badges.append(chip(`audio · ${((a.latent_t||0)/40).toFixed(1)} s · ${Number(a.token_count).toLocaleString()} tokens`,"audio"));}
 if(group.visual&&group.audio)badges.append(chip(group.paired?"paired files":"appearance + voice"));
 const summary=document.createElement("summary");summary.textContent="Details";details.append(summary);
 for(const [label,value] of [["Subject",group.primary.subject_name],["Appearance",group.visual?.appearance],["Voice",group.audio?.voice_description],["Notes",group.primary.description]])if(value){const p=document.createElement("p");p.textContent=`${label}: ${value}`;details.append(p);}
 details.append(badges,files);const detailButton=button(selected.has(group.key)?"Selected":"Select",()=>{selected.has(group.key)?selected.delete(group.key):selected.add(group.key);localStorage.setItem("skeba-refmod-selection",JSON.stringify([...selected]));renderCatalog();renderSelection();});detailButton.classList.toggle("selected",selected.has(group.key));const editButton=button("Edit",()=>edit(group).catch(error=>status(error.message,true)));editButton.setAttribute("aria-label",`Edit ${group.name}`);actions.append(detailButton,editButton,button("Export",()=>exportGroup(group)),button("Delete",()=>removeGroup(group).catch(error=>status(error.message,true))));body.append(name,actions,details);card.append(preview,body);$("assets").append(card);}
 $("empty").hidden=shown.length>0;$("library-count").textContent=`${groups.length} RefMods · ${groups.filter(group=>group.visual&&group.audio).length} appearance + voice`;
}
async function removeGroup(group){
 if(busy)return;
 if(!confirm(`Delete ${group.name}?\n\n${group.files.join("\n")}\n\nThis deletes the entire RefMod, including all bundle members. Characters using it will need another attachment. Source media and thumbnails are kept.`))return;
 const selections=group.files.map(file=>selection(group.rows.find(row=>row.file===file)));
 await request("/api/h3-refmods/records",{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({selections})});
 if(existing&&group.files.includes(existing.file)){reset();showView(false);}await refresh();status(`Deleted ${group.name}.`);
}
async function refresh(){await loadCollections();catalog=await request("/api/h3-refmods/records");groups=groupCatalog(catalog);renderFolders();renderCatalog();await loadSharedSelection();renderSelection();}
async function edit(group){
 if(busy)return;if(group.primary.error)throw new Error(group.primary.error);const row=group.primary;
 const meta=await request(`/api/h3-refmods/detail?file=${encodeURIComponent(row.file)}&member=${row.member??""}`);const members=meta.kind==="bundle"?meta.members:[meta];const visual=members.find(m=>m.kind!=="audio");
 let voice=members.find(m=>m.kind==="audio");existing=selection(row);companion=group.paired&&group.audio?selection(group.audio):null;
 if(companion){const voiceMeta=await request(`/api/h3-refmods/detail?file=${encodeURIComponent(companion.file)}&member=${companion.member??""}`);voice=voiceMeta.kind==="bundle"?voiceMeta.members[companion.member]:voiceMeta;}
 sources=[];frameRows=Array.from({length:visual?.latent_t||0},(_,index)=>({index,keep:true}));storedVoice=voice||null;previewData={frames:[],audio:null};syncFrames();
 $("reference_type").value=group.primary.reference_type||"character";$("collection").value=group.primary.collection||"";
 $("name").value=group.name;$("file").value=group.paired?group.key+"_edited.safetensors":row.file.replace(/\.safetensors$/i,"_edited.safetensors");$("subject_name").value=visual?.subject_name||voice?.subject_name||"";$("appearance").value=visual?.appearance||"";$("voice_description").value=voice?.voice_description||"";$("description").value=visual?.description||voice?.description||"";$("mode").value=visual?.mode==="encode"?"encode":"training";
 for(const key of ["resolution","grid","video_seconds","steps","audio_seconds"])if(meta.skeba_studio?.[key]!=null)$(key).value=meta.skeba_studio[key];
 keepVoice=true;$("overwrite").checked=false;$("overwrite-row").hidden=false;$("retrain").checked=false;$("clip-note").hidden=!visual||visual.latent_t<=1;
 if(meta.skeba_studio?.video_seconds==null&&meta.skeba_studio?.video_frames)$("video_seconds").value=meta.skeba_studio.video_frames/24;
 $("stored-info").textContent=`${frameRows.length} stored frames${voice?" + voice":""}${companion?" · saves as one appearance + voice bundle; original files are preserved":""}`;$("editor-title").textContent=`Editing ${group.name}`;$("show-editor").textContent=`Editing ${group.name}`;
 renderStored();renderSources();modeChanged();baseline=snapshot();remember();showView(true);status("Kept frames are copied exactly. Generate previews to inspect the stored appearance and voice.");
}
function reset(){if(busy)return;$("editor").reset();keepVoice=true;sources=[];existing=null;companion=null;frameRows=[];storedVoice=null;previewData={frames:[],audio:null};baseline="";$("overwrite-row").hidden=true;$("editor-title").textContent="Create RefMod";$("show-editor").textContent="Create / Edit";$("stored-info").textContent="Add sources to build an appearance and/or voice reference.";renderStored();renderSources();modeChanged();remember();showView(true);status("");}
function setBusy(value){busy=value;$("editor-fields").disabled=value;$("new").disabled=value;$("cancel-edit").disabled=value;$("import-mod").disabled=value;$("job-progress").hidden=!value;summary();}
async function poll(job){try{const history=await request(`/history/${job.id}`),run=history[job.id];if(!run){const queue=await request('/queue');const running=(queue.queue_running||[]).some(entry=>entry[1]===job.id);status(`${running?(job.kind==="preview"?"Decoding previews":"Encoding / refining RefMod"):"Waiting in queue"} · ${Math.floor((Date.now()-(job.started||Date.now()))/1000)}s elapsed`);setTimeout(()=>poll(job),1500);return;}if(run.status?.status_str==="error"){const event=run.status.messages?.find(([type])=>type==="execution_error");throw new Error(event?.[1]?.exception_message||JSON.stringify(run.status.messages));}
 localStorage.removeItem("skeba-refmod-job");setBusy(false);
 if(job.kind==="preview"){const data=run.outputs?.["3"]?.refmod_preview?.[0];if(!data)throw new Error("Preview job returned no preview data.");previewData=data;renderStored();remember();status("Stored-frame and voice previews are ready.");return;}
 const file=run.outputs?.["3"]?.text?.[0];if(!file)throw new Error("Job ended without a saved RefMod. Check ComfyUI history.");await refresh();const saved=groups.find(group=>group.files.includes(file));if(saved)await edit(saved);else {baseline=snapshot();summary();}status(`Saved ${file}. Select it in the RefMod library to add its tags to your prompt guide.`);$("result").replaceChildren();
 }catch(error){localStorage.removeItem("skeba-refmod-job");setBusy(false);status(error.message,true);}}
async function queue(kind){if(busy||uploading)return;try{const data=spec();const inputs={spec:JSON.stringify(data)},prompt={};const visual=kind==="preview"?frameRows.length>0:sources.some(source=>source.kind!=="audio"),voice=kind==="preview"?Boolean(storedVoice):sources.some(source=>source.kind==="audio"||(source.kind==="video"&&source.include_audio));
 if(visual||voice){const graph=await workflowModels([...(visual?["vae"]:[]),...(voice?["audio_vae"]:[])]);Object.assign(prompt,graph.prompt);Object.assign(inputs,graph.inputs);}
 prompt["3"]={class_type:kind==="preview"?"SkebaRefModPreview":"SkebaRefModStudio",inputs};remember();const result=await request("/prompt",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt})});const job={id:result.prompt_id,kind,started:Date.now()};localStorage.setItem("skeba-refmod-job",JSON.stringify(job));setBusy(true);status(kind==="preview"?"Queued stored-frame and audio preview decoding...":"Queued training / encoding. Watch progress in ComfyUI's queue.");poll(job);
 }catch(error){status(error.message,true);}}

$("editor").onsubmit=event=>{event.preventDefault();queue("save");};$("preview").onclick=()=>queue("preview");$("upload").onchange=()=>upload([...$("upload").files]);
const zone=document.querySelector(".upload-zone");zone.ondragover=event=>event.preventDefault();zone.ondrop=event=>{event.preventDefault();upload([...event.dataTransfer.files]);};
$("new").onclick=reset;$("refresh").onclick=()=>refresh().catch(error=>status(error.message,true));$("search").oninput=renderCatalog;$("kind-filter").onchange=renderCatalog;$("mode").onchange=modeChanged;
$("show-library").onclick=$("back").onclick=()=>showView(false);$("show-editor").onclick=()=>showView(true);$("editor").addEventListener("change",remember);
async function init(){const draft=JSON.parse(localStorage.getItem("skeba-refmod-draft")||"null");
 if(draft){for(const id of fields)if(draft[id]!=null)$(id).value=draft[id];sources=draft.sources||[];existing=draft.existing||null;companion=draft.companion||null;frameRows=draft.frameRows||[];storedVoice=draft.storedVoice||null;keepVoice=draft.keep_voice??draft.audio_action!=="remove";if(draft.video_seconds==null&&draft.video_frames)$("video_seconds").value=draft.video_frames/24;previewData=draft.previewData||{frames:[],audio:null};$("overwrite").checked=Boolean(existing)&&!draft.overwrite;$("overwrite-row").hidden=!existing;$("retrain").checked=Boolean(draft.retrain);}
 if(existing){$("editor-title").textContent=`Editing ${$("name").value}`;$("show-editor").textContent=`Editing ${$("name").value}`;$("cancel-edit").hidden=false;}renderStored();renderSources();modeChanged();summary();await refresh();const raw=localStorage.getItem("skeba-refmod-job");if(raw){const job=raw.startsWith("{")?JSON.parse(raw):{id:raw,kind:"save"};setBusy(true);status("Watching queued RefMod job...");poll(job);}}
init().catch(error=>status(error.message,true));

$("remove-frames").onclick=()=>{frameRows.forEach(row=>row.keep=false);syncFrames();renderStored();remember();};
$("cancel-edit").onclick=()=>{if(busy)return;reset();localStorage.removeItem("skeba-refmod-draft");showView(false);};
$("import-mod").onclick=()=>$("import-files").click();
$("import-files").onchange=async()=>{if(busy)return;try{const files=[...$("import-files").files];if(!files.length)return;const data=new FormData();files.forEach(file=>data.append("files",file));status("Importing RefMods...");const result=await request("/api/h3-refmods/import",{method:"POST",body:data});await refresh();showView(false);status(`Imported ${result.files.length} RefMod(s).`);}catch(error){status(error.message,true);}finally{$("import-files").value="";}};
function workflowModels(fields){return new Promise((resolve,reject)=>{
 const channel=new BroadcastChannel("skeba-refmod-workflow");const id=Date.now()+"-"+Math.random().toString(36).slice(2);const params=new URLSearchParams(location.search);
 let settle;const replies=[];const timer=setTimeout(()=>{channel.close();reject(new Error("Open ComfyUI, connect VAEs to SKEBA RefMod Studio Create / Edit, then use its Open RefMod Library button."));},5000);
 channel.onmessage=({data})=>{if(data.id!==id||data.type!=="models")return;replies.push(data);if(settle)return;settle=setTimeout(()=>{clearTimeout(timer);channel.close();if(replies.length!==1){reject(new Error("Multiple ComfyUI tabs are open. Use Open RefMod Library on the intended Studio node."));return;}data.error?reject(new Error(data.error)):resolve(data);},params.get("client")?0:200);};
 channel.postMessage({type:"request-models",id,fields,client:params.get("client"),node:params.get("node")});
});}

async function loadCollections(){const data=await request("/api/h3-references/collections");const current=$("collection-filter").value;$("collections").replaceChildren(...data.collections.map(name=>new Option(name,name)));$("collection-filter").replaceChildren(new Option("All collections",""),...data.collections.map(name=>new Option(name,name)));$("collection-filter").value=current;}
$("type-filter").onchange=$("collection-filter").onchange=renderCatalog;

let otherSelected=[],selectionRequest=0;
const selectionKeys=["skeba-reference-selection","skeba-built-in-selection","skeba-refmod-selection"];
function guideRecords(){return [...otherSelected,...groups.filter(group=>selected.has(group.key)).map(refmodGuideRecord)];}
function guideText(){return referenceGuideText(guideRecords());}
function renderSelection(){renderReferenceGuide(guideRecords(),Object.fromEntries(["selection-empty","selection-guide","clear-selection","copy-selection"].map(id=>[id,$(id)])));}
async function loadSharedSelection(){
 const version=++selectionRequest;
 const standard=new Set(JSON.parse(localStorage.getItem(selectionKeys[0])||"[]"));
 const builtin=new Set(JSON.parse(localStorage.getItem(selectionKeys[1])||"[]"));
 const [references,characters]=await Promise.all([
  standard.size?request("/api/h3-references/records"):Promise.resolve({records:[]}),
  builtin.size?request("/api/h3-built-in-references/records"):Promise.resolve({records:[]})
 ]);
 if(version!==selectionRequest)return;
 otherSelected=[...references.records.filter(record=>standard.has(record.id)),...characters.records.filter(record=>builtin.has(record.tag)).map(record=>({...record,id:`built-in:${record.library_tag}`,tag:record.library_tag,category:record.collection||"built-in-characters",reference_type:"character",built_in:true}))];
 renderSelection();
}
$("clear-selection").onclick=()=>{selectionRequest++;otherSelected=[];selected.clear();selectionKeys.forEach(key=>localStorage.removeItem(key));renderCatalog();renderSelection();};
$("copy-selection").onclick=async()=>{try{await navigator.clipboard.writeText(guideText());status("Reference guide copied.");}catch(error){status(error.message,true);}};
async function exportGroup(group){
 const name=group.name.replace(/[<>:"/\\|?*\x00-\x1f]/g,"_")+".safetensors";
 const url="/api/h3-refmods/export?"+new URLSearchParams({name:group.name,selections:JSON.stringify(group.files.map(file=>selection(group.rows.find(row=>row.file===file))))});
 try{if(window.showSaveFilePicker){const handle=await window.showSaveFilePicker({suggestedName:name,types:[{description:"RefMod",accept:{"application/octet-stream":[".safetensors"]}}]});const response=await fetch(url);if(!response.ok){const data=await response.json();throw new Error(data.error||"Export failed.");}await response.body.pipeTo(await handle.createWritable());status("RefMod exported.");}
 else{const link=document.createElement("a");link.href=url;link.download=name;document.body.append(link);link.click();link.remove();}}
 catch(error){if(error.name!=="AbortError")status(error.message,true);}
}

window.addEventListener("storage",event=>{if(!selectionKeys.includes(event.key)&&event.key!==null)return;selected.clear();for(const key of JSON.parse(localStorage.getItem("skeba-refmod-selection")||"[]"))selected.add(key);renderCatalog();loadSharedSelection().catch(error=>status(error.message,true));});
window.addEventListener("focus",()=>loadSharedSelection().catch(error=>status(error.message,true)));
