const apiRoot = "/api/h3-built-in-references/records";
const state = { records: [], selected: new Set() };
const elements = Object.fromEntries([
    "built-in-folder", "built-in-search", "built-in-count", "built-in-empty",
    "built-in-records", "built-in-selection-count", "refresh-built-ins",
    "copy-built-in-selection", "copy-built-in-voice-selection",
    "built-in-sort-field", "built-in-sort-direction", "toast",
].map((id) => [id, document.getElementById(id)]));

async function request(url) {
    const response = await fetch(url);
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
    return `^${record.tag}^`;
}

function voiceTag(record) {
    return `~${record.tag}~`;
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
        && [record.name, record.actor, record.franchise, record.status]
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
    const actor = document.createElement("strong");
    actor.textContent = record.actor || "Actor not listed";
    details.append(actor, document.createTextNode(record.franchise ? ` | ${record.franchise}` : ""));

    const actions = document.createElement("div");
    actions.className = "built-in-meta";
    actions.append(
        button("Copy character tag", () => copyTags([record])),
        button("Copy voice tag", () => copyTags([record], voiceTag, "Voice tag")),
    );
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
    elements["built-in-selection-count"].textContent = count
        ? `${count} character${count === 1 ? "" : "s"} selected`
        : "No characters selected";
    elements["copy-built-in-selection"].disabled = count === 0;
    elements["copy-built-in-voice-selection"].disabled = count === 0;
}

async function copyTags(records, formatTag = referenceTag, label = "Tag") {
    try {
        await navigator.clipboard.writeText(records.map(formatTag).join("\n"));
        toast(`${records.length === 1 ? label : `${label}s`} copied.`);
    } catch (error) {
        toast("Could not copy character tags.", true);
    }
}

function copySelection() {
    return copyTags(state.records.filter((record) => state.selected.has(record.tag)));
}

function copyVoiceSelection() {
    return copyTags(
        state.records.filter((record) => state.selected.has(record.tag)),
        voiceTag,
        "Voice tag",
    );
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
elements["copy-built-in-selection"].addEventListener("click", copySelection);
elements["copy-built-in-voice-selection"].addEventListener("click", copyVoiceSelection);

loadRecords();
