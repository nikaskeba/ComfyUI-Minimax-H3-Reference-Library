let activePopout=null;
const apiRoot = "/api/h3-built-in-references/records";
const state = { records: [], selected: new Set(JSON.parse(localStorage.getItem("skeba-built-in-selection")||"[]")) };
const libraryTagMode = document.body.dataset.builtInTagMode === "library";
const elements = Object.fromEntries([
    "built-in-folder", "built-in-search", "built-in-count", "built-in-empty",
    "built-in-records", "built-in-selection-count", "refresh-built-ins",
    "clear-built-in-selection", "copy-built-in-selection",
    "built-in-selection-empty", "built-in-selection-guide",
    "built-in-sort-field", "built-in-sort-direction", "toast",
].map((id) => [id, document.getElementById(id)]));

const collectionOptions=document.createElement("datalist");collectionOptions.id="built-in-collections";document.body.append(collectionOptions);
const collectionFilter=document.createElement("select");collectionFilter.setAttribute("aria-label","Collection");
const collectionFilterLabel=document.createElement("label");collectionFilterLabel.textContent="Collection";collectionFilterLabel.append(collectionFilter);elements["built-in-folder"].parentElement.after(collectionFilterLabel);collectionFilter.onchange=renderRecords;
async function loadCollections(){const data=await request("/api/h3-references/collections");const current=collectionFilter.value;collectionOptions.replaceChildren(...data.collections.map(name=>new Option(name,name)));collectionFilter.replaceChildren(new Option("All collections",""),...data.collections.map(name=>new Option(name,name)));collectionFilter.value=current;}

async function request(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
}

async function loadRecords() {
    try {
        const payload = await request(apiRoot);
        if (!Array.isArray(payload.records)) {
            throw new Error("The built-in character catalog returned an invalid response.");
        }
        activePopout?.close();
        state.records = payload.records;
        await loadCollections();
        const tags = new Set(state.records.map((record) => record.tag));
        state.selected = new Set([...state.selected].filter((tag) => tags.has(tag)));
        renderFolderFilter();
        renderRecords();
    } catch (error) {
        toast(error.message, true);
    }
}

function referenceTag(record) {
    return libraryTagMode ? `{${record.library_tag || `${record.tag}_BC`}}` : `^${record.tag}^`;
}

function voiceTag(record) {
    return libraryTagMode ? `\u00a7${record.library_tag || `${record.tag}_BC`}\u00a7` : `~${record.tag}~`;
}

function renderFolderFilter() {
    const current = elements["built-in-folder"].value;
    const folders = [...new Set(state.records.map((record) => record.folder))];
    const all = document.createElement("option");
    all.value = "";
    all.textContent = "All statuses";
    const options = folders.map((folder) => {
        const record = state.records.find((item) => item.folder === folder);
        const option = document.createElement("option");
        option.value = folder;
        option.textContent = record?.status || folder;
        return option;
    });
    elements["built-in-folder"].replaceChildren(all, ...options);
    elements["built-in-folder"].value = folders.includes(current) ? current : "";
}

function filteredRecords() {
    const folder = elements["built-in-folder"].value;
    const query = elements["built-in-search"].value.trim().toLowerCase();
    const sortField = elements["built-in-sort-field"].value;
    const direction = elements["built-in-sort-direction"].value === "desc" ? -1 : 1;
    return state.records.filter((record) => (!collectionFilter.value || record.collection === collectionFilter.value) && (!folder || record.folder === folder)
        && [record.name, record.actor, record.franchise, record.status, record.image_context]
            .some((value) => (value || "").toLowerCase().includes(query)))
        .sort((left, right) => direction * compareRecords(left, right, sortField));
}

function compareRecords(left, right, field) {
    return (left[field] || "").localeCompare(right[field] || "", undefined, { sensitivity: "base" })
        || left.name.localeCompare(right.name, undefined, { sensitivity: "base" })
        || left.actor.localeCompare(right.actor, undefined, { sensitivity: "base" })
        || left.franchise.localeCompare(right.franchise, undefined, { sensitivity: "base" });
}

function renderRecords() {
    elements["built-in-records"].querySelectorAll("audio").forEach(audio=>audio.pause());
    const records = filteredRecords();
    const groups = new Map();
    for (const record of records) {
        if (!groups.has(record.folder)) groups.set(record.folder, []);
        groups.get(record.folder).push(record);
    }
    elements["built-in-records"].replaceChildren(...[...groups.entries()].map(([folder, items]) => {
        const group = document.createElement("div");
        group.className = "built-in-group";
        const heading = document.createElement("div");
        heading.className = "built-in-group-heading";
        const title = document.createElement("h3");
        title.textContent = items[0]?.status || folder;
        const count = document.createElement("span");
        count.textContent = `${items.length} character${items.length === 1 ? "" : "s"}`;
        const list = document.createElement("div");
        list.className = "built-in-list";
        list.append(...items.map(recordRow));
        heading.append(title, count);
        group.append(heading, list);
        return group;
    }));
    elements["built-in-count"].textContent = records.length === state.records.length
        ? `${state.records.length} character${state.records.length === 1 ? "" : "s"}`
        : `${records.length} of ${state.records.length} characters`;
    elements["built-in-empty"].hidden = records.length !== 0;
    renderSelectionState();
}

const icons = {
 image:'<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
 voice:'<path d="M4 10v4m4-8v12m4-16v20m4-16v12m4-8v4"/>',
 folder:'<path d="M3 20V5h6l2 3h10v12z"/>',
 edit:'<path d="m15 4 5 5M4 20l5-1L21 7l-5-5L4 14z"/>',
 copy:'<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
 more:'<circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>',
 close:'<path d="m6 6 12 12M6 18 18 6"/>',
 play:'<path d="m7 4 14 8-14 8z"/>', pause:'<path d="M8 4v16M16 4v16"/>',
};
function icon(name){const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");svg.setAttribute("viewBox","0 0 24 24");svg.setAttribute("aria-hidden","true");svg.innerHTML=icons[name];return svg;}
function iconButton(name,label,action){const control=button("",action);control.className="builtin-icon-button";control.title=label;control.setAttribute("aria-label",label);control.append(icon(name));return control;}
function popout(record,title){
 activePopout?.close();
 const dialog=document.createElement("dialog");dialog.className="builtin-popout";
 const header=document.createElement("header"),heading=document.createElement("h2"),body=document.createElement("div");heading.id="builtin-popout-title";heading.textContent=`${record.name} · ${title}`;dialog.setAttribute("aria-labelledby",heading.id);
 header.append(heading,iconButton("close","Close editor",()=>dialog.close()));dialog.append(header,body);document.body.append(dialog);
 dialog.addEventListener("close",()=>{dialog.querySelectorAll("audio").forEach(audio=>audio.pause());dialog.remove();if(activePopout===dialog)activePopout=null;});
 dialog.addEventListener("click",event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
 activePopout=dialog;dialog.showModal();return {dialog,body};
}
function editImage(record){
 const {body}=popout(record,"Image reference");
 if(record.image_url){const image=document.createElement("img");image.src=record.image_url;image.alt=`${record.name} reference`;body.append(image);}
 body.append(button(record.has_image?"Replace image":"Add image",()=>chooseImage(record)));
 if(record.has_image){
  body.append(button("Remove image",()=>removeImage(record)));
  const label=document.createElement("label"),input=document.createElement("textarea");label.textContent="Image context (visual reference only)";input.rows=4;input.value=record.image_context||"";input.placeholder="Describe which appearance details to use.";label.append(input);
  const save=button("Save image context",()=>saveImageContext(record,input,save));save.disabled=true;input.oninput=()=>save.disabled=input.value.trim()===(record.image_context||"").trim();body.append(label,save);
 }
}
function editVoice(record){
 const {body}=popout(record,"Voice reference");
 if(record.audio_url){const audio=document.createElement("audio");audio.controls=true;audio.preload="metadata";audio.src=record.audio_url;audio.setAttribute("aria-label",`${record.name} voice reference`);body.append(audio);}
 body.append(button(record.has_audio?"Replace voice clip":"Add voice clip",()=>chooseAudio(record)));
 if(record.has_audio)body.append(button("Remove voice clip",()=>removeAudio(record)));
 const tag=document.createElement("code");tag.textContent=voiceTag(record);body.append(tag);
}
function editCollection(record){
 const {dialog,body}=popout(record,"Collection");const label=document.createElement("label"),input=document.createElement("input");label.textContent="Collection (optional)";input.value=record.collection||"";input.setAttribute("list","built-in-collections");input.placeholder="Choose or enter a collection";label.append(input);
 const save=button("Save collection",async()=>{save.disabled=true;try{const result=await request(`${apiRoot}/${record.attachment_id}/collection`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({collection:input.value})});record.collection=result.collection;await loadCollections();dialog.close();renderRecords();toast("Collection saved.");}catch(error){save.disabled=false;toast(error.message,true);}});body.append(label,save);input.focus();
}
function mediaColumn(kind,title){const column=document.createElement("div");column.className=`builtin-column builtin-${kind}`;const heading=document.createElement("div");heading.className="builtin-column-title";heading.append(icon(kind),document.createTextNode(title));column.append(heading);return column;}
function recordRow(record) {
 const row=document.createElement("article");row.className=`built-in-row builtin-compact${state.selected.has(record.tag)?" selected":""}`;
 const checkLabel=document.createElement("label"),check=document.createElement("input");checkLabel.className="built-in-check";check.type="checkbox";check.checked=state.selected.has(record.tag);check.setAttribute("aria-label",`Select ${record.name}`);check.onchange=()=>{check.checked?state.selected.add(record.tag):state.selected.delete(record.tag);row.classList.toggle("selected",check.checked);renderSelectionState();};checkLabel.append(check);
 const identity=document.createElement("div");identity.className="builtin-person";
 const portrait=document.createElement(record.image_url?"img":"div");portrait.className="builtin-portrait";
 if(record.image_url){portrait.src=record.image_url;portrait.alt="";portrait.loading="lazy";}else{portrait.textContent=record.name.split(/\s+/).slice(0,2).map(word=>word[0]).join("");portrait.setAttribute("aria-hidden","true");}
 const info=document.createElement("div"),name=document.createElement("strong"),tag=document.createElement("code"),details=document.createElement("span");info.className="built-in-identity";name.textContent=record.name;tag.textContent=referenceTag(record);details.className="builtin-portrayal";details.textContent=[record.actor,record.franchise].filter(Boolean).join(" · ");info.append(name,tag,details);identity.append(portrait,info);
 const image=mediaColumn("image","Image"),voice=mediaColumn("voice","Voice"),collection=mediaColumn("folder","Collection");
 if(libraryTagMode){
  const imageLine=document.createElement("div");imageLine.className="builtin-inline";const status=document.createElement("span");status.className=record.has_image?"builtin-attached":"builtin-empty";status.textContent=record.has_image?"✓ Attached":"No image";imageLine.append(status,iconButton("edit",`Edit image for ${record.name}`,()=>editImage(record)));image.append(imageLine);
  const voiceLine=document.createElement("div");voiceLine.className="builtin-inline";
  if(record.audio_url){const audio=document.createElement("audio");audio.src=record.audio_url;audio.preload="none";const play=iconButton("play",`Play voice for ${record.name}`,()=>{if(audio.paused){document.querySelectorAll('.builtin-compact audio').forEach(other=>{if(other!==audio)other.pause();});audio.play().catch(error=>toast(error.message,true));}else audio.pause();});const update=()=>{play.replaceChildren(icon(audio.paused?"play":"pause"));play.setAttribute("aria-label",`${audio.paused?"Play":"Pause"} voice for ${record.name}`);};audio.onplay=audio.onpause=audio.onended=update;voiceLine.append(play,audio);}
  const voiceStatus=document.createElement("span");voiceStatus.textContent=record.has_audio?"Voice clip":"No clip";voiceStatus.className="builtin-empty";voiceLine.append(voiceStatus,iconButton("edit",`Edit voice for ${record.name}`,()=>{row.querySelectorAll("audio").forEach(audio=>audio.pause());editVoice(record);}));voice.append(voiceLine);
 }else{image.append(document.createTextNode("Built-in likeness"));voice.append(document.createTextNode("Built-in voice"));}
 const collectionButton=button(record.collection||"Add collection",()=>editCollection(record));collectionButton.className="builtin-collection-button";collectionButton.setAttribute("aria-label",`Edit collection for ${record.name}`);collection.append(collectionButton);
 const actions=document.createElement("div");actions.className="builtin-row-actions";
 actions.append(iconButton("copy",`Copy character and voice for ${record.name}`,()=>copyCharacterGuide([record])),iconButton("more",`More options for ${record.name}`,()=>{const {body}=popout(record,"Tags & details");const text=document.createElement("p");text.textContent=portrayalText(record);body.append(text,button("Copy character + voice",()=>copyCharacterGuide([record])));for(const [label,value] of [["Character",referenceTag(record)],["Voice",voiceTag(record)]]){const code=document.createElement("code");code.textContent=`${label}: ${value}`;body.append(code);}}));
 row.append(checkLabel,identity,image,voice,collection,actions);return row;
}

function button(text, onClick) {
    const element = document.createElement("button");
    element.type = "button";
    element.className = "secondary";
    element.textContent = text;
    element.addEventListener("click", onClick);
    return element;
}

function renderSelectionState() {
    localStorage.setItem("skeba-built-in-selection",JSON.stringify([...state.selected]));
    const count = state.selected.size;
    if (libraryTagMode) {
        window.dispatchEvent(new CustomEvent("skeba-built-in-selection-change", {
            detail: { records: selectedRecords() },
        }));
        return;
    }
    elements["built-in-selection-count"].textContent = count
        ? `${count} character${count === 1 ? "" : "s"} selected`
        : "No characters selected";
    elements["built-in-selection-empty"].hidden = count !== 0;
    elements["built-in-selection-guide"].hidden = count === 0;
    elements["clear-built-in-selection"].disabled = count === 0;
    elements["copy-built-in-selection"].disabled = count === 0;
    elements["built-in-selection-guide"].replaceChildren(
        ...selectedRecords().map(selectionItem),
    );
}

function chooseImage(record) {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.addEventListener("change", async () => {
        const file = input.files?.[0];
        if (!file) return;
        const form = new FormData();
        form.append("image", file);
        try {
            await request(`${apiRoot}/${record.attachment_id}/image`, { method: "PUT", body: form });
            await loadRecords();
            toast(`Reference image attached to ${record.name}.`);
        } catch (error) {
            toast(error.message, true);
        }
    }, { once: true });
    input.click();
}

async function removeImage(record) {
    if (!window.confirm(`Remove the optional reference image for ${record.name}?`)) return;
    try {
        await request(`${apiRoot}/${record.attachment_id}/image`, { method: "DELETE" });
        await loadRecords();
        toast(`Reference image removed from ${record.name}.`);
    } catch (error) {
        toast(error.message, true);
    }
}

function chooseAudio(record) {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "audio/*";
    input.addEventListener("change", async () => {
        const file = input.files?.[0];
        if (!file) return;
        const form = new FormData();
        form.append("audio", file);
        try {
            await request(`${apiRoot}/${record.attachment_id}/audio`, { method: "PUT", body: form });
            await loadRecords();
            toast(`Voice clip attached to ${record.name}.`);
        } catch (error) {
            toast(error.message, true);
        }
    }, { once: true });
    input.click();
}

async function removeAudio(record) {
    if (!window.confirm(`Remove the optional reference audio for ${record.name}?`)) return;
    try {
        await request(`${apiRoot}/${record.attachment_id}/audio`, { method: "DELETE" });
        await loadRecords();
        toast(`Voice clip removed from ${record.name}.`);
    } catch (error) {
        toast(error.message, true);
    }
}

async function saveImageContext(record, input, saveButton) {
    const originalText = saveButton.textContent;
    saveButton.disabled = true;
    saveButton.textContent = "Saving...";
    try {
        await request(`${apiRoot}/${record.attachment_id}/image-context`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image_context: input.value.trim() }),
        });
        await loadRecords();
        toast(`Image context saved for ${record.name}.`);
    } catch (error) {
        saveButton.disabled = false;
        saveButton.textContent = originalText;
        toast(error.message, true);
    }
}

function selectedRecords() {
    const byTag = new Map(state.records.map((record) => [record.tag, record]));
    return [...state.selected].map((tag) => byTag.get(tag)).filter(Boolean);
}

function portrayalText(record) {
    const playedBy = record.actor ? `Played by ${record.actor}` : "Actor not listed";
    return record.franchise ? `${playedBy} | ${record.franchise}` : playedBy;
}

function guideLine(record) {
    return `${referenceTag(record)} Voice: ${voiceTag(record)}   ${portrayalText(record)}`;
}

function selectionItem(record) {
    const item = document.createElement("div");
    item.className = "selection-item";
    const tags = document.createElement("div");
    tags.className = "selection-tags";
    const character = document.createElement("code");
    character.textContent = referenceTag(record);
    const voice = document.createElement("code");
    voice.className = "voice-tag";
    voice.textContent = `Voice: ${voiceTag(record)}`;
    const details = document.createElement("div");
    details.className = "selection-details";
    details.textContent = portrayalText(record);
    const collectionLabel=document.createElement("label"),collection=document.createElement("input");
    collectionLabel.textContent="Collection (optional)";collection.value=record.collection||"";collection.setAttribute("list","built-in-collections");collection.placeholder="Choose or enter a collection";
    const saveCollection=button("Save collection",async()=>{try{const result=await request(`${apiRoot}/${record.attachment_id}/collection`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({collection:collection.value})});record.collection=result.collection;collection.value=result.collection;await loadCollections();renderSelectionState();toast("Collection saved.");}catch(error){toast(error.message,true);}});
    collectionLabel.append(collection,saveCollection);details.append(collectionLabel);
    tags.append(character, voice);
    item.append(tags, details);
    return item;
}

async function copyCharacterGuide(records) {
    try {
        await navigator.clipboard.writeText(records.map(guideLine).join("\n"));
        toast(`${records.length === 1 ? "Character guide" : "Character guides"} copied.`);
    } catch (error) {
        toast("Could not copy the character guide.", true);
    }
}

function copySelection() {
    return copyCharacterGuide(selectedRecords());
}

let toastTimer;
function toast(message, isError = false) {
    clearTimeout(toastTimer);
    elements.toast.textContent = message;
    elements.toast.className = `visible${isError ? " error" : ""}`;
    toastTimer = setTimeout(() => { elements.toast.className = ""; }, 3500);
}

elements["built-in-search"].addEventListener("input", renderRecords);
elements["built-in-folder"].addEventListener("change", renderRecords);
elements["built-in-sort-field"].addEventListener("change", renderRecords);
elements["built-in-sort-direction"].addEventListener("change", renderRecords);
elements["refresh-built-ins"].addEventListener("click", loadRecords);
if (elements["clear-built-in-selection"]) {
    elements["clear-built-in-selection"].addEventListener("click", () => {
        state.selected.clear();
        renderRecords();
    });
}
if (elements["copy-built-in-selection"]) {
    elements["copy-built-in-selection"].addEventListener("click", copySelection);
}
if (libraryTagMode) {
    window.addEventListener("skeba-clear-all-reference-selection", () => {
        state.selected.clear();
        renderRecords();
    });
}

loadRecords();

window.addEventListener("storage",event=>{if(event.key!=="skeba-built-in-selection"&&event.key!==null)return;state.selected=new Set(JSON.parse(localStorage.getItem("skeba-built-in-selection")||"[]"));renderRecords();});
