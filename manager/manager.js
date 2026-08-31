const apiRoot = "/api/h3-references/records";
const imageExtensions = new Set(["jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff"]);
const audioExtensions = new Set(["aac", "flac", "m4a", "mp3", "mp4", "ogg", "opus", "wav", "webm"]);
const categoryPriority = ["character", "narrator", "location", "voice", "object", "style", "other"];
const referenceTypes = ["character", "location", "object", "music", "uncategorized"];
const state = { records: [], drafts: [], selected: new Set() };

const elements = Object.fromEntries([
    "library-count", "category-filter", "type-filter", "media-filter", "search", "add-reference", "clear-drafts", "drop-zone", "bulk-files",
    "drafts", "draft-actions", "draft-summary", "import-drafts", "refresh", "empty-state",
    "records", "record-dialog", "record-form", "dialog-title", "close-dialog", "cancel-dialog",
    "clear-selection", "copy-selection", "selection-empty", "selection-guide", "record-id", "tag", "category", "reference-type",
    "new-category-row", "new-category", "category-options",
    "image-file", "image-description", "audio-file", "audio-description",
    "remove-image-row", "remove-image", "remove-audio-row", "remove-audio", "save-record", "toast",
].map((id) => [id, document.getElementById(id)]));

function extension(name) {
    return name.includes(".") ? name.split(".").pop().toLowerCase() : "";
}

function stem(name) {
    return name.replace(/\.[^.]+$/, "");
}

function tagFromName(name) {
    const tag = stem(name).trim().replace(/\s+/g, "_").replace(/[^A-Za-z0-9_-]/g, "_").replace(/_+/g, "_");
    return tag || "reference";
}

function mediaKind(file) {
    const ext = extension(file.name);
    if (file.type.startsWith("image/") || imageExtensions.has(ext)) return "image";
    if (file.type.startsWith("audio/") || audioExtensions.has(ext)) return "audio";
    return null;
}

async function request(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
}

async function loadRecords() {
    try {
        const payload = await request(apiRoot);
        state.records = payload.records;
        const recordIds = new Set(state.records.map((record) => record.id));
        state.selected = new Set([...state.selected].filter((recordId) => recordIds.has(recordId)));
        renderCategoryFilter();
        renderCategoryChoices();
        renderRecords();
        renderSelectionGuide();
    } catch (error) {
        toast(error.message, true);
    }
}

function renderRecords() {
    const query = elements.search.value.trim().toLowerCase();
    const category = elements["category-filter"].value;
    const referenceType = elements["type-filter"].value;
    const media = elements["media-filter"].value;
    const records = state.records.filter((record) => (!category || record.category === category)
        && (!referenceType || normalizedReferenceType(record) === referenceType)
        && matchesMediaFilter(record, media)
        && [record.tag, record.category, normalizedReferenceType(record), record.image_description, record.audio_description]
            .some((value) => (value || "").toLowerCase().includes(query)));
    elements["library-count"].textContent = `${state.records.length} managed reference${state.records.length === 1 ? "" : "s"}`;
    elements.records.replaceChildren(...groupedRecordCards(records));
    elements["empty-state"].hidden = records.length !== 0;
}

function matchesMediaFilter(record, media) {
    if (media === "paired") return record.has_image && record.has_audio;
    if (media === "image") return record.has_image && !record.has_audio;
    if (media === "audio") return record.has_audio && !record.has_image;
    return true;
}

function groupedRecordCards(records) {
    const groups = new Map();
    for (const record of records) {
        const category = record.category || "other";
        if (!groups.has(category)) groups.set(category, []);
        groups.get(category).push(record);
    }
    return [...groups.entries()]
        .sort(([left], [right]) => compareCategories(left, right))
        .map(([category, categoryRecords]) => {
            const group = document.createElement("div");
            group.className = "category-group";
            const heading = document.createElement("div");
            heading.className = "category-group-heading";
            const title = document.createElement("h3");
            title.textContent = categoryHeading(category);
            const count = document.createElement("span");
            count.textContent = `${categoryRecords.length} reference${categoryRecords.length === 1 ? "" : "s"}`;
            const typeGroups = document.createElement("div");
            typeGroups.className = "reference-type-groups";
            typeGroups.append(...groupByReferenceType(categoryRecords).map(([referenceType, typeRecords]) => {
                const typeGroup = document.createElement("section");
                typeGroup.className = "reference-type-group";
                const typeHeading = document.createElement("div");
                typeHeading.className = "reference-type-heading";
                const typeTitle = document.createElement("h4");
                typeTitle.textContent = referenceTypeHeading(referenceType);
                const typeCount = document.createElement("span");
                typeCount.textContent = `${typeRecords.length}`;
                const grid = document.createElement("div");
                grid.className = "record-grid";
                grid.append(...typeRecords.map(recordCard));
                typeHeading.append(typeTitle, typeCount);
                typeGroup.append(typeHeading, grid);
                return typeGroup;
            }));
            heading.append(title, count);
            group.append(heading, typeGroups);
            return group;
        });
}

function normalizedReferenceType(record) {
    return referenceTypes.includes(record?.reference_type) ? record.reference_type : "uncategorized";
}

function groupByReferenceType(records) {
    const groups = new Map();
    for (const record of records) {
        const referenceType = normalizedReferenceType(record);
        if (!groups.has(referenceType)) groups.set(referenceType, []);
        groups.get(referenceType).push(record);
    }
    return [...groups.entries()].sort(
        ([left], [right]) => referenceTypes.indexOf(left) - referenceTypes.indexOf(right),
    );
}

function renderCategoryFilter() {
    const current = elements["category-filter"].value;
    const categories = [...new Set(state.records.map((record) => record.category || "other"))]
        .sort(compareCategories);
    const all = document.createElement("option");
    all.value = "";
    all.textContent = "All categories";
    const options = categories.map((category) => {
        const option = document.createElement("option");
        option.value = category;
        option.textContent = categoryLabel(category);
        return option;
    });
    elements["category-filter"].replaceChildren(all, ...options);
    elements["category-filter"].value = categories.includes(current) ? current : "";
}

function libraryCategories(extra = "") {
    return [...new Set([
        ...state.records.map((record) => record.category || "other"),
        extra,
    ].filter(Boolean))].sort(compareCategories);
}

function renderCategoryChoices(selected = elements.category.value) {
    const categories = libraryCategories(selected && selected !== "__new__" ? selected : "");
    const options = categories.map((category) => {
        const option = document.createElement("option");
        option.value = category;
        option.textContent = categoryLabel(category);
        return option;
    });
    const create = document.createElement("option");
    create.value = "__new__";
    create.textContent = "Create new category...";
    elements.category.replaceChildren(...options, create);
    elements.category.value = categories.includes(selected) ? selected : (categories[0] || "__new__");
    const creating = elements.category.value === "__new__";
    elements["new-category-row"].hidden = !creating;
    elements["new-category"].required = creating;

    const suggestions = [...new Set([...categoryPriority, ...categories])].sort(compareCategories).map((category) => {
        const option = document.createElement("option");
        option.value = category;
        return option;
    });
    elements["category-options"].replaceChildren(...suggestions);
}

function selectedCategory() {
    const value = elements.category.value === "__new__" ? elements["new-category"].value : elements.category.value;
    return value.trim().toLowerCase().replace(/\s+/g, "_");
}

function suggestedCategory(referenceType) {
    return referenceType === "uncategorized" ? "other" : referenceType;
}

function recordCard(record) {
    const card = document.createElement("article");
    card.className = "record-card";
    const preview = document.createElement("div");
    preview.className = "record-preview";
    if (record.has_image) {
        const image = document.createElement("img");
        image.src = `${record.image_url}?v=${encodeURIComponent(record.updated_at || "")}`;
        image.alt = record.image_description || record.tag;
        image.loading = "lazy";
        preview.append(image);
    } else {
        const audioMark = document.createElement("span");
        audioMark.className = "audio-only";
        audioMark.textContent = "Audio";
        preview.append(audioMark);
    }

    const body = document.createElement("div");
    body.className = "record-body";
    const title = document.createElement("div");
    title.className = "record-title";
    const code = document.createElement("code");
    code.textContent = `{${record.tag}}`;
    const voiceCode = document.createElement("code");
    voiceCode.className = "voice-tag";
    voiceCode.textContent = `Voice: §${record.tag}§`;
    const badges = document.createElement("div");
    badges.className = "media-badges";
    badges.append(badge(categoryLabel(record.category || "other"), "category"));
    badges.append(badge(referenceTypeLabel(normalizedReferenceType(record)), "reference-type"));
    if (record.has_image) badges.append(badge("Image", ""));
    if (record.has_audio) badges.append(badge("Audio", "audio"));
    title.append(code);
    if (record.has_audio || record.audio_description) title.append(voiceCode);
    title.append(badges);

    const description = document.createElement("div");
    description.className = "description";
    description.textContent = [record.image_description, record.audio_description].filter(Boolean).join(" / ") || "No description";
    body.append(title, description);
    if (record.has_audio) {
        const audio = document.createElement("audio");
        audio.controls = true;
        audio.preload = "none";
        audio.src = `${record.audio_url}?v=${encodeURIComponent(record.updated_at || "")}`;
        body.append(audio);
    }

    const actions = document.createElement("div");
    actions.className = "card-actions";
    const selected = state.selected.has(record.id);
    const select = button(selected ? "Selected" : "Select", `select-reference${selected ? " selected" : ""}`, () => toggleSelection(record.id));
    const copyVoice = button("Copy voice", "secondary", () => copyVoiceTag(record));
    const edit = button("Edit", "secondary", () => openEditor(record));
    const remove = button("Delete", "danger", () => removeRecord(record));
    actions.append(select);
    if (record.has_audio || record.audio_description) actions.append(copyVoice);
    actions.append(edit, remove);
    body.append(actions);
    card.append(preview, body);
    return card;
}

function badge(text, className) {
    const element = document.createElement("span");
    element.className = `badge ${className}`;
    element.textContent = text;
    return element;
}

function categoryLabel(category) {
    return (category || "other").replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function categoryHeading(category) {
    const plurals = {
        character: "Characters",
        narrator: "Narrators",
        location: "Locations",
        voice: "Voices",
        object: "Objects",
        style: "Styles",
        other: "Other",
    };
    return plurals[category] || categoryLabel(category);
}

function referenceTypeLabel(referenceType) {
    return categoryLabel(referenceType || "uncategorized");
}

function referenceTypeHeading(referenceType) {
    const plurals = {
        character: "Characters",
        location: "Locations",
        object: "Objects",
        music: "Music",
        uncategorized: "Uncategorized",
    };
    return plurals[referenceType] || referenceTypeLabel(referenceType);
}

function compareCategories(left, right) {
    const leftIndex = categoryPriority.indexOf(left);
    const rightIndex = categoryPriority.indexOf(right);
    const leftRank = leftIndex === -1 ? categoryPriority.length : leftIndex;
    const rightRank = rightIndex === -1 ? categoryPriority.length : rightIndex;
    return leftRank - rightRank || left.localeCompare(right);
}

function button(text, className, onClick) {
    const element = document.createElement("button");
    element.type = "button";
    element.className = className;
    element.textContent = text;
    element.addEventListener("click", onClick);
    return element;
}

function addDraftFiles(files) {
    const groups = new Map(state.drafts.map((draft) => [draft.key, draft]));
    for (const file of files) {
        const kind = mediaKind(file);
        if (!kind) continue;
        const key = stem(file.name).toLowerCase();
        const draft = groups.get(key) || {
            key,
            tag: tagFromName(file.name),
            category: "other",
            reference_type: "uncategorized",
            image: null,
            audio: null,
        };
        draft[kind] = file;
        groups.set(key, draft);
    }
    state.drafts = [...groups.values()];
    renderDrafts();
}

function renderDrafts() {
    elements.drafts.replaceChildren(...state.drafts.map((draft, index) => {
        const row = document.createElement("div");
        row.className = "draft-row";
        const tagLabel = document.createElement("label");
        tagLabel.textContent = "Tag";
        const tagInput = document.createElement("input");
        tagInput.value = draft.tag;
        tagInput.pattern = "[A-Za-z0-9_-]+";
        tagInput.addEventListener("input", () => { draft.tag = tagInput.value.trim(); });
        tagLabel.append(tagInput);
        const categoryLabelElement = document.createElement("label");
        categoryLabelElement.textContent = "Category";
        const categoryInput = document.createElement("input");
        categoryInput.value = draft.category;
        categoryInput.setAttribute("list", "category-options");
        categoryInput.pattern = "[A-Za-z0-9_-]+";
        categoryInput.addEventListener("input", () => { draft.category = categoryInput.value.trim().toLowerCase().replace(/\s+/g, "_"); });
        categoryLabelElement.append(categoryInput);
        const typeLabel = document.createElement("label");
        typeLabel.textContent = "Reference type";
        const typeSelect = document.createElement("select");
        typeSelect.append(...referenceTypes.map((referenceType) => {
            const option = document.createElement("option");
            option.value = referenceType;
            option.textContent = referenceTypeLabel(referenceType);
            return option;
        }));
        typeSelect.value = draft.reference_type || "uncategorized";
        typeSelect.addEventListener("change", () => { draft.reference_type = typeSelect.value; });
        typeLabel.append(typeSelect);
        row.append(tagLabel, categoryLabelElement, typeLabel, draftMedia("Image", draft.image), draftMedia("Audio", draft.audio));
        row.dataset.index = index;
        return row;
    }));
    const hasDrafts = state.drafts.length > 0;
    elements.drafts.hidden = !hasDrafts;
    elements["draft-actions"].hidden = !hasDrafts;
    elements["clear-drafts"].hidden = !hasDrafts;
    elements["draft-summary"].textContent = `${state.drafts.length} reference draft${state.drafts.length === 1 ? "" : "s"}`;
}

function draftMedia(label, file) {
    const element = document.createElement("div");
    element.className = "draft-media";
    const strong = document.createElement("strong");
    strong.textContent = `${label}: `;
    element.append(strong, document.createTextNode(file ? file.name : "None"));
    return element;
}

async function importDrafts() {
    const tags = state.drafts.map((draft) => draft.tag);
    if (tags.some((tag) => !/^[A-Za-z0-9_-]+$/.test(tag))) return toast("Every draft needs a valid tag.", true);
    if (state.drafts.some((draft) => !/^[A-Za-z0-9_-]+$/.test(draft.category))) return toast("Every draft needs a valid category.", true);
    if (new Set(tags).size !== tags.length) return toast("Draft tags must be unique.", true);
    elements["import-drafts"].disabled = true;
    try {
        for (const draft of state.drafts) {
            const data = new FormData();
            data.append("tag", draft.tag);
            data.append("category", draft.category);
            data.append("reference_type", draft.reference_type || "uncategorized");
            if (draft.image) data.append("image", draft.image);
            if (draft.audio) data.append("audio", draft.audio);
            await request(apiRoot, { method: "POST", body: data });
        }
        const count = state.drafts.length;
        clearDrafts();
        await loadRecords();
        toast(`Imported ${count} reference${count === 1 ? "" : "s"}.`);
    } catch (error) {
        toast(error.message, true);
        await loadRecords();
    } finally {
        elements["import-drafts"].disabled = false;
    }
}

function clearDrafts() {
    state.drafts = [];
    elements["bulk-files"].value = "";
    renderDrafts();
}

function openEditor(record = null) {
    elements["record-form"].reset();
    elements["record-id"].value = record?.id || "";
    elements["dialog-title"].textContent = record ? "Edit reference" : "Add reference";
    elements.tag.value = record?.tag || "";
    renderCategoryChoices(record?.category || "other");
    elements["reference-type"].value = normalizedReferenceType(record);
    elements["image-description"].value = record?.image_description || "";
    elements["audio-description"].value = record?.audio_description || "";
    elements["remove-image-row"].hidden = !record?.has_image;
    elements["remove-audio-row"].hidden = !record?.has_audio;
    elements["record-dialog"].showModal();
}

async function saveRecord(event) {
    event.preventDefault();
    const category = selectedCategory();
    if (!/^[A-Za-z0-9_-]+$/.test(category)) return toast("Enter a valid category.", true);
    const recordId = elements["record-id"].value;
    const data = new FormData();
    data.append("tag", elements.tag.value.trim());
    data.append("category", category);
    data.append("reference_type", elements["reference-type"].value);
    data.append("image_description", elements["image-description"].value.trim());
    data.append("audio_description", elements["audio-description"].value.trim());
    if (elements["image-file"].files[0]) data.append("image", elements["image-file"].files[0]);
    if (elements["audio-file"].files[0]) data.append("audio", elements["audio-file"].files[0]);
    data.append("remove_image", String(elements["remove-image"].checked));
    data.append("remove_audio", String(elements["remove-audio"].checked));
    elements["save-record"].disabled = true;
    try {
        await request(recordId ? `${apiRoot}/${recordId}` : apiRoot, { method: recordId ? "PUT" : "POST", body: data });
        elements["record-dialog"].close();
        await loadRecords();
        toast(recordId ? "Reference updated." : "Reference added.");
    } catch (error) {
        toast(error.message, true);
    } finally {
        elements["save-record"].disabled = false;
    }
}

async function removeRecord(record) {
    if (!window.confirm(`Delete {${record.tag}} and its managed media?`)) return;
    try {
        await request(`${apiRoot}/${record.id}`, { method: "DELETE" });
        await loadRecords();
        toast("Reference deleted.");
    } catch (error) {
        toast(error.message, true);
    }
}

function toggleSelection(recordId) {
    if (state.selected.has(recordId)) {
        state.selected.delete(recordId);
    } else {
        state.selected.add(recordId);
    }
    renderRecords();
    renderSelectionGuide();
}

function selectedGroups() {
    const groups = new Map();
    for (const record of state.records.filter((item) => state.selected.has(item.id))) {
        const category = record.category || "other";
        if (!groups.has(category)) groups.set(category, []);
        groups.get(category).push(record);
    }
    return [...groups.entries()]
        .sort(([left], [right]) => compareCategories(left, right))
        .map(([category, records]) => [
            category,
            groupByReferenceType(records).map(([referenceType, typeRecords]) => [
                referenceType,
                typeRecords.sort((left, right) => left.tag.localeCompare(right.tag)),
            ]),
        ]);
}

function renderSelectionGuide() {
    const groups = selectedGroups();
    const hasSelection = groups.length > 0;
    elements["selection-empty"].hidden = hasSelection;
    elements["selection-guide"].hidden = !hasSelection;
    elements["clear-selection"].disabled = !hasSelection;
    elements["copy-selection"].disabled = !hasSelection;
    elements["selection-guide"].replaceChildren(...groups.map(([category, typeGroups]) => {
        const group = document.createElement("div");
        group.className = "selection-group";
        const heading = document.createElement("h3");
        heading.textContent = categoryHeading(category);
        group.append(heading, ...typeGroups.map(([referenceType, records]) => {
            const typeGroup = document.createElement("div");
            typeGroup.className = "selection-type-group";
            const typeHeading = document.createElement("h4");
            typeHeading.textContent = referenceTypeHeading(referenceType);
            typeGroup.append(typeHeading, ...records.map(selectionItem));
            return typeGroup;
        }));
        return group;
    }));
}

function selectionItem(record) {
    const item = document.createElement("div");
    item.className = "selection-item";
    const tag = document.createElement("code");
    tag.textContent = `{${record.tag}}`;
    item.append(tag);
    if (record.has_audio || record.audio_description) {
        const voiceTag = document.createElement("code");
        voiceTag.className = "voice-tag";
        voiceTag.textContent = `Voice: §${record.tag}§`;
        item.append(voiceTag);
    }
    if (record.image_description) item.append(descriptionLine("Image", record.image_description));
    if (record.audio_description) item.append(descriptionLine("Voice", record.audio_description));
    if (!record.image_description && !record.audio_description) item.append(descriptionLine("Description", "None"));
    return item;
}

function descriptionLine(label, description) {
    const line = document.createElement("div");
    line.className = "selection-description";
    line.textContent = `${label}: ${description}`;
    return line;
}

function selectionGuideText() {
    return selectedGroups().map(([category, typeGroups]) => {
        const lines = [categoryHeading(category).toUpperCase()];
        for (const [referenceType, records] of typeGroups) {
            lines.push("", referenceTypeHeading(referenceType).toUpperCase());
            for (const record of records) {
                lines.push(`{${record.tag}}`);
                if (record.has_audio || record.audio_description) lines.push(`Voice tag: §${record.tag}§`);
                if (record.image_description) lines.push(`Image: ${record.image_description}`);
                if (record.audio_description) lines.push(`Voice: ${record.audio_description}`);
                if (!record.image_description && !record.audio_description) lines.push("Description: None");
                lines.push("");
            }
        }
        return lines.join("\n").trimEnd();
    }).join("\n\n");
}

async function copySelectionGuide() {
    try {
        await navigator.clipboard.writeText(selectionGuideText());
        toast("Reference guide copied.");
    } catch (error) {
        toast("Could not copy the reference guide.", true);
    }
}

async function copyVoiceTag(record) {
    try {
        await navigator.clipboard.writeText(`§${record.tag}§`);
        toast("Voice tag copied.");
    } catch (error) {
        toast("Could not copy the voice tag.", true);
    }
}

let toastTimer;
function toast(message, isError = false) {
    clearTimeout(toastTimer);
    elements.toast.textContent = message;
    elements.toast.className = `visible${isError ? " error" : ""}`;
    toastTimer = setTimeout(() => { elements.toast.className = ""; }, 3500);
}

elements.search.addEventListener("input", renderRecords);
elements["category-filter"].addEventListener("change", renderRecords);
elements["type-filter"].addEventListener("change", renderRecords);
elements["media-filter"].addEventListener("change", renderRecords);
elements.refresh.addEventListener("click", loadRecords);
elements["clear-selection"].addEventListener("click", () => {
    state.selected.clear();
    renderRecords();
    renderSelectionGuide();
});
elements["copy-selection"].addEventListener("click", copySelectionGuide);
elements["add-reference"].addEventListener("click", () => openEditor());
elements.category.addEventListener("change", () => {
    const creating = elements.category.value === "__new__";
    elements["new-category-row"].hidden = !creating;
    elements["new-category"].required = creating;
    if (creating) elements["new-category"].focus();
});
elements["reference-type"].addEventListener("change", () => {
    if (elements["record-id"].value) return;
    renderCategoryChoices(suggestedCategory(elements["reference-type"].value));
});
elements["close-dialog"].addEventListener("click", () => elements["record-dialog"].close());
elements["cancel-dialog"].addEventListener("click", () => elements["record-dialog"].close());
elements["record-form"].addEventListener("submit", saveRecord);
elements["bulk-files"].addEventListener("change", (event) => addDraftFiles(event.target.files));
elements["clear-drafts"].addEventListener("click", clearDrafts);
elements["import-drafts"].addEventListener("click", importDrafts);
elements["drop-zone"].addEventListener("dragover", (event) => { event.preventDefault(); elements["drop-zone"].classList.add("dragging"); });
elements["drop-zone"].addEventListener("dragleave", () => elements["drop-zone"].classList.remove("dragging"));
elements["drop-zone"].addEventListener("drop", (event) => {
    event.preventDefault();
    elements["drop-zone"].classList.remove("dragging");
    addDraftFiles(event.dataTransfer.files);
});

loadRecords();
