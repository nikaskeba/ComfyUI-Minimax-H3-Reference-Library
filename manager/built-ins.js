const apiRoot = "/api/h3-built-in-references/records";
const state = { records: [], selected: new Set() };
const libraryTagMode = document.body.dataset.builtInTagMode === "library";
const elements = Object.fromEntries([
    "built-in-folder", "built-in-search", "built-in-count", "built-in-empty",
    "built-in-records", "built-in-selection-count", "refresh-built-ins",
    "clear-built-in-selection", "copy-built-in-selection",
    "built-in-selection-empty", "built-in-selection-guide",
    "built-in-sort-field", "built-in-sort-direction", "toast",
].map((id) => [id, document.getElementById(id)]));

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
        state.records = payload.records;
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
    return state.records.filter((record) => (!folder || record.folder === folder)
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

function recordRow(record) {
    const row = document.createElement("article");
    row.className = `built-in-row${state.selected.has(record.tag) ? " selected" : ""}`;
    const checkLabel = document.createElement("label");
    checkLabel.className = "built-in-check";
    checkLabel.title = `Select ${record.name} played by ${record.actor}`;
    const check = document.createElement("input");
    check.type = "checkbox";
    check.checked = state.selected.has(record.tag);
    check.addEventListener("change", () => {
        if (check.checked) state.selected.add(record.tag);
        else state.selected.delete(record.tag);
        row.classList.toggle("selected", check.checked);
        renderSelectionState();
    });
    checkLabel.append(check);

    const identity = document.createElement("div");
    identity.className = "built-in-identity";
    const name = document.createElement("strong");
    name.textContent = record.name;
    const tag = document.createElement("code");
    tag.textContent = referenceTag(record);
    const voice = document.createElement("code");
    voice.className = "voice-tag";
    voice.textContent = `Voice: ${voiceTag(record)}`;
    identity.append(name, tag, voice);

    const details = document.createElement("div");
    details.className = "built-in-details";
    details.textContent = portrayalText(record);
    if (libraryTagMode && record.has_image) {
        const contextEditor = document.createElement("label");
        contextEditor.className = "built-in-image-context";
        const contextTitle = document.createElement("span");
        contextTitle.textContent = "Image context (visual reference only)";
        const contextInput = document.createElement("textarea");
        contextInput.rows = 2;
        contextInput.value = record.image_context || "";
        contextInput.placeholder = "Example: Use the face and hairstyle; ignore the plain white background.";
        const saveContext = button("Save image context", () => saveImageContext(
            record, contextInput, saveContext));
        saveContext.disabled = true;
        contextInput.addEventListener("input", () => {
            saveContext.disabled = contextInput.value.trim() === (record.image_context || "").trim();
        });
        contextEditor.append(contextTitle, contextInput, saveContext);
        details.append(contextEditor);
    }

    const actions = document.createElement("div");
    actions.className = "built-in-meta";
    if (libraryTagMode) {
        if (record.image_url) {
            const preview = document.createElement("img");
            preview.className = "built-in-image-preview";
            preview.src = record.image_url;
            preview.alt = `${record.name} reference`;
            actions.append(preview);
        }
        actions.append(button(record.has_image ? "Replace image" : "Add image", () => chooseImage(record)));
        if (record.has_image) actions.append(button("Remove image", () => removeImage(record)));
    }
    actions.append(button("Copy character + voice", () => copyCharacterGuide([record])));
    row.append(checkLabel, identity, details, actions);
    return row;
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
