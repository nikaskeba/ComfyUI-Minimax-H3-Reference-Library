async function requestJSON(url, options={}) {
    const response = await fetch(url, options);
    const text = await response.text();
    let result;
    try { result = JSON.parse(text); }
    catch { throw new Error(`${url} returned ${response.status} with a non-JSON response. Restart ComfyUI after updating the nodes, then refresh this page.`); }
    if (!response.ok) throw new Error(result.error || `Request failed (${response.status}): ${url}`);
    return result;
}

// Shared saved/built-in attachment editor. RefMod creation stays in external tools.
export async function refmodFields(record = {}) {
    const root = document.createElement("fieldset");
    const legend = document.createElement("legend"); legend.textContent = "Reference sources / RefMods"; root.append(legend);
    const catalog = await requestJSON("/api/h3-refmods/records");
    const invalid = catalog.filter(row => row.error);
    if (invalid.length) { const note = document.createElement("p"); note.textContent = "Unreadable RefMods: " + invalid.map(row => row.file + ": " + row.error).join("; "); root.append(note); }
    const controls = {};
    for (const channel of ["appearance", "voice"]) {
        const label = document.createElement("label"); label.textContent = `${channel} source`;
        const source = document.createElement("select");
        for (const [value, text] of [["media", "Existing media"], ["refmod", "RefMod"]]) source.add(new Option(text, value));
        source.value = record[channel + "_source"] || "media";
        const search = document.createElement("input"); search.placeholder = `Search ${channel} RefMods`;
        const picker = document.createElement("select");
        const info = document.createElement("div");
        const preview = document.createElement("img"); preview.style.cssText = "max-width:180px;max-height:120px;object-fit:contain"; preview.alt = "RefMod preview";
        const initial = record[channel + "_refmod"];
        let selected = initial ? JSON.stringify({file: initial.file, member: initial.member ?? null}) : "";
        let rows = catalog.filter(row => channel === "voice" ? row.kind === "audio" : ["image", "video"].includes(row.kind));
        const key = row => JSON.stringify({file: row.file, member: row.member ?? null});
        const update = () => {
            picker.disabled = search.disabled = source.value !== "refmod";
            const row = rows.find(row => key(row) === picker.value);
            info.textContent = row ? `${row.kind} · ${row.token_count} tokens` : (picker.value ? "Attachment missing or incompatible" : "Choose an attachment");
            preview.hidden = !row?.preview || source.value !== "refmod";
            if (!preview.hidden) preview.src = `/api/h3-refmods/preview?file=${encodeURIComponent(row.file)}&member=${row.member ?? ""}`;
        };
        const populate = () => {
            picker.replaceChildren(new Option("Select RefMod…", ""));
            for (const row of rows.filter(row => key(row) === selected || `${row.file} ${row.name}`.toLowerCase().includes(search.value.toLowerCase())))
                picker.add(new Option(`${row.file}${row.member == null ? "" : " · member " + row.member} — ${row.name}`, key(row)));
            if (selected && !rows.some(row => key(row) === selected)) picker.add(new Option("Missing attachment: " + selected, selected));
            picker.value = selected; update();
        };
        root.addEventListener("refmods-created", async event => {
            let refreshed;
            try { refreshed = await requestJSON("/api/h3-refmods/records"); }
            catch (error) { info.textContent = error.message; return; }
            rows = refreshed.filter(row => channel === "voice" ? row.kind === "audio" : ["image", "video"].includes(row.kind));
            const created = rows.find(row => row.file === event.detail);
            if (created) { selected = key(created); source.value = "refmod"; }
            populate();
        });
        source.onchange = update; search.oninput = populate;
        picker.onchange = () => { selected = picker.value; update(); };
        label.append(source, search, picker, info, preview); root.append(label);
        controls[channel] = {source, picker}; populate();
    }
    const studio = document.createElement("a"); studio.href = "/h3-refmods"; studio.target = "_blank"; studio.rel = "noopener";
    studio.textContent = "Create, train and edit RefMods in RefMod Studio"; root.append(studio);
    const refresh = document.createElement("button"); refresh.type = "button"; refresh.textContent = "Refresh attachments";
    refresh.onclick = () => root.dispatchEvent(new CustomEvent("refmods-created", {detail: ""})); root.append(refresh);
    let mode = null;
    return {element: root, addTabs(standard) {
        mode = [record.appearance_source, record.voice_source].includes("refmod") ? "refmod" : "media";
        const tabs = document.createElement("div"); tabs.className = "reference-source-tabs";
        const standardTab = document.createElement("button"); standardTab.type = "button"; standardTab.textContent = "Standard Reference";
        const modTab = document.createElement("button"); modTab.type = "button"; modTab.textContent = "RefMod";
        const update = () => {
            standard.hidden = mode !== "media"; root.hidden = mode !== "refmod";
            standardTab.className = mode === "media" ? "primary" : "secondary";
            modTab.className = mode === "refmod" ? "primary" : "secondary";
        };
        standardTab.onclick = () => { mode = "media"; update(); };
        modTab.onclick = () => {
            mode = "refmod";
            for (const {source, picker} of Object.values(controls)) if (picker.value) { source.value = "refmod"; source.dispatchEvent(new Event("change")); }
            if (Object.values(controls).every(({source}) => source.value === "media")) {
                const channel = record.reference_type === "music" ? "voice" : "appearance";
                controls[channel].source.value = "refmod"; controls[channel].source.dispatchEvent(new Event("change"));
            }
            update();
        };
        tabs.append(standardTab, modTab); root.before(tabs);
        tabs.id = "refmod-source-tabs"; update();
    }, read() {
        const result = {};
        for (const [channel, {source, picker}] of Object.entries(controls)) {
            result[channel + "_source"] = mode === "media" ? "media" : source.value;
            result[channel + "_refmod"] = picker.value ? JSON.parse(picker.value) : null;
        }
        return result;
    }};
}

export async function editBuiltInRefmods(record, onSaved) {
    const fields = await refmodFields(record);
    const dialog = document.createElement("dialog");
    const title = document.createElement("h2"); title.textContent = `RefMods: ${record.name}`;
    const save = document.createElement("button"); save.textContent = "Save sources";
    const close = document.createElement("button"); close.textContent = "Cancel";
    const error = document.createElement("p"); error.setAttribute("role", "alert");
    close.onclick = () => dialog.close();
    save.onclick = async () => {
        save.disabled = true;
        try {
            await requestJSON(`/api/h3-built-in-references/records/${record.attachment_id}/refmods`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(fields.read())});
            await onSaved(); dialog.close();
        } catch (e) { error.textContent = e.message; } finally { save.disabled = false; }
    };
    dialog.append(title, fields.element, error, save, close); document.body.append(dialog);
    dialog.onclose = () => dialog.remove(); dialog.showModal();
}

