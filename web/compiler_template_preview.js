import {api} from "../../scripts/api.js";
import {groupCatalog, refmodTag} from "../../h3-references/static/refmod-catalog.js";

export function createTemplatePreview(node, getTemplates, showExamples) {
    const panel = document.createElement("details");
    const heading = document.createElement("summary"); heading.textContent = "Preview with a reference";
    const note = document.createElement("p");
    note.textContent = "Illustrative numbering from a single-reference example—not your workflow's assignments. No model runs or media encoding. Templates use [[name]] and [[subject]]; reference tags select the example only.";
    const search = document.createElement("input"); search.type = "search"; search.placeholder = "Search name or paste {character} / §voice§"; search.setAttribute("aria-label", "Search preview references");
    const picker = document.createElement("select"); picker.setAttribute("aria-label", "Preview reference");
    for (const el of [search, picker]) el.style.cssText = "width:100%;box-sizing:border-box;margin:4px 0";
    const refresh = document.createElement("button"); refresh.type = "button"; refresh.textContent = "Refresh references";
    const audio = document.createElement("select"); audio.setAttribute("aria-label", "Preview audio usage");
    for (const value of ["reference", "reuse"]) audio.add(new Option("Audio: " + value, value));
    const video = document.createElement("select"); video.setAttribute("aria-label", "Preview video usage");
    for (const value of ["reference", "motion_reference", "continuation", "editing"]) video.add(new Option("Video: " + value, value));
    const info = document.createElement("div"), status = document.createElement("p"), output = document.createElement("pre");
    status.setAttribute("role", "status"); output.style.cssText = "white-space:pre-wrap;overflow-wrap:anywhere;font:12px monospace";
    const full = document.createElement("details"), title = document.createElement("summary"); title.textContent = "Complete example prompt"; full.append(title, output);
    panel.append(heading, note, search, picker, refresh, audio, video, info, status, full);
    let records = [], selected = null, loaded = false, timer, revision = 0, disposed = false;
    const saved = () => node.properties?.skeba_template_preview_reference;
    async function request(path, options) {
        const response = await api.fetchApi(path, options);
        if (!(response.headers.get("content-type") || "").includes("json")) throw Error("Preview unavailable. Restart ComfyUI after updating the nodes.");
        const data = await response.json();
        if (!response.ok) throw Error(data.error || "Preview could not load.");
        return data;
    }
    function choose() {
        selected = records.find(row => row.id === picker.value) || null;
        node.properties ??= {}; node.properties.skeba_template_preview_reference = selected?.id || "";
        node.graph?.setDirtyCanvas(true, true);
        update();
    }
    function draw() {
        const query = search.value.replace(/[{}§]/g, "").trim().toLowerCase();
        const shown = records.filter(row => `${row.tag} ${row.name} ${row.source}`.toLowerCase().includes(query));
        picker.replaceChildren(new Option(shown.length ? "Choose a reference" : "No matching references", ""), ...shown.map(row => new Option(`${row.name} — ${row.source} {${row.tag}}`, row.id)));
        picker.value = shown.some(row => row.id === selected?.id) ? selected.id : "";
    }
    async function load() {
        status.textContent = "Loading references…";
        const paths = ["/api/h3-references/records", "/api/h3-built-in-references/records", "/api/h3-refmods/records"];
        const results = await Promise.allSettled(paths.map(path => request(path)));
        if (disposed) return;
        records = [];
        results.forEach((result, index) => {
            if (result.status !== "fulfilled") return;
            if (index === 2) {
                for (const group of groupCatalog(result.value)) {
                    if (group.primary.error) continue;
                    const thumb = group.rows.find(row => row.preview);
                    records.push({id: "refmod:" + group.key, tag: refmodTag(group), name: group.name, source: "RefMod", hasAudio: Boolean(group.audio),
                        image: thumb ? "/api/h3-refmods/preview?" + new URLSearchParams({file: thumb.file, member: thumb.member ?? ""}) : null});
                }
            } else for (const row of result.value.records || []) records.push({
                id: (index ? "builtin:" : "saved:") + (row.id || row.tag), tag: index ? row.library_tag || row.tag + "_BC" : row.tag,
                name: row.name || row.tag, source: index ? "Built-in" : "Library", hasAudio: Boolean(row.has_audio), image: row.image_url});
        });
        loaded = true; selected = records.find(row => row.id === saved()) || null; draw();
        status.textContent = results.some(r => r.status === "rejected") ? "Some reference sources could not load. Refresh to retry." : "Choose a reference to preview.";
        if (selected) update();
    }
    function update() {
        clearTimeout(timer); const current = ++revision;
        showExamples({}); output.textContent = ""; info.replaceChildren();
        if (!selected) {status.textContent = "Choose a reference to preview."; return;}
        const chosen = selected;
        if (chosen.image) {
            const image = document.createElement("img"); image.src = chosen.image; image.alt = chosen.name;
            image.style.cssText = "max-width:100px;max-height:100px;object-fit:contain";
            image.onerror = () => image.remove(); info.append(image);
        }
        const name = document.createElement("strong"); name.textContent = " " + chosen.name; info.append(name);
        status.textContent = "Updating example…";
        timer = setTimeout(async () => {
            try {
                const data = await request("/api/h3-references/compiler-template-preview", {method:"POST", headers:{"Content-Type":"application/json"},
                    body:JSON.stringify({tag:chosen.tag, preview_voice:chosen.hasAudio, compiler_templates:getTemplates(), audio_usage:audio.value, video_usage:video.value})});
                if (disposed || current !== revision) return;
                const voice = document.createElement("p"); voice.textContent = "Voice description: " + (data.voice_description || "None saved."); info.append(voice);
                status.textContent = data.has_audio ? "Example compiled. Numbers are illustrative." : "No attached audio for this example; no audio slot is invented.";
                output.textContent = data.prompt; showExamples(data.examples);
            } catch (error) {
                if (!disposed && current === revision) status.textContent = error.message;
            }
        }, 250);
    }
    picker.onchange = choose; search.oninput = draw; refresh.onclick = load;
    audio.onchange = video.onchange = update;
    panel.ontoggle = () => {if (panel.open && !loaded) load();};
    return {element:panel, update, restore:() => {selected = records.find(row => row.id === saved()) || null; draw(); if (selected) update();},
        dispose:() => {disposed = true; revision++; clearTimeout(timer);}};
}
