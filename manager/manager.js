const apiRoot = "/api/h3-references/records";
const imageExtensions = new Set(["jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff"]);
const audioExtensions = new Set(["aac", "flac", "m4a", "mp3", "mp4", "ogg", "opus", "wav", "webm"]);
const videoExtensions = new Set(["avi", "m4v", "mkv", "mov", "mp4", "mpeg", "mpg", "webm"]);
const categoryPriority = ["character", "narrator", "location", "voice", "object", "style", "other"];
const referenceTypes = ["character", "location", "object", "music", "video", "uncategorized"];
const assignableReferenceTypes = referenceTypes.filter((referenceType) => referenceType !== "uncategorized");
const mediaByReferenceType = {
    character: ["image", "audio"],
    location: ["image"],
    object: ["image", "audio"],
    music: ["audio"],
    video: ["video"],
    uncategorized: ["image", "audio", "video"],
};
const state = { records: [], categories: [], drafts: [], selected: new Set() };

const elements = Object.fromEntries([
    "library-count", "category-filter", "type-filter", "media-filter", "search", "add-reference", "clear-drafts", "drop-zone", "bulk-files",
    "drafts", "draft-actions", "draft-summary", "import-drafts", "import-error", "refresh", "empty-state",
    "records", "record-dialog", "record-form", "dialog-title", "close-dialog", "cancel-dialog",
    "clear-selection", "copy-selection", "selection-empty", "selection-guide", "record-id", "tag", "category", "reference-type",
    "new-category-row", "new-category", "category-options",
    "image-fields", "audio-fields", "video-fields", "image-file", "image-description", "audio-file", "audio-description", "video-file", "video-description",
    "remove-image-row", "remove-image", "remove-audio-row", "remove-audio", "remove-video-row", "remove-video", "record-error", "save-record", "toast",
].map((id) => [id, document.getElementById(id)]));

function extension(name) {
    return name.includes(".") ? name.split(".").pop().toLowerCase() : "";
}

function stem(name) {
    return name.replace(/\.[^.]+$/, "");
}

function normalizeTag(value) {
    let tag = (value || "").trim();
    if (tag.startsWith("{") && tag.endsWith("}")) tag = tag.slice(1, -1).trim();
    return tag.replace(/[^A-Za-z0-9_-]+/g, "_").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
}

function normalizeCategory(value) {
    return (value || "").trim().toLowerCase()
        .replace(/[^A-Za-z0-9_-]+/g, "_")
        .replace(/_+/g, "_")
        .replace(/^_+|_+$/g, "");
}

function allowedMedia(referenceType) {
    return mediaByReferenceType[referenceType] || mediaByReferenceType.uncategorized;
}

function presentMedia(source) {
    return ["image", "audio", "video"].filter((kind) => source?.[kind] || source?.[`has_${kind}`]);
}

function supportedReferenceTypes(source) {
    const media = presentMedia(source);
    if (!media.length) return [...assignableReferenceTypes];
    return assignableReferenceTypes.filter(
        (referenceType) => media.every((kind) => allowedMedia(referenceType).includes(kind)),
    );
}

function tagFromName(name) {
    return normalizeTag(stem(name)) || "reference";
}

function mediaKind(file) {
    const ext = extension(file.name);
    if (file.type.startsWith("image/")) return "image";
    if (file.type.startsWith("video/")) return "video";
    if (file.type.startsWith("audio/")) return "audio";
    if (imageExtensions.has(ext)) return "image";
    if (videoExtensions.has(ext)) return "video";
    if (audioExtensions.has(ext)) return "audio";
    return null;
}

async function request(url, options = {}) {
    const response = await fetch(url, options);
    const responseText = await response.text();
    let payload = {};
    try {
        payload = responseText ? JSON.parse(responseText) : {};
    } catch (error) {
        payload = {};
    }
    if (!response.ok) {
        const plainText = responseText && !/<(?:!doctype|html|body)\b/i.test(responseText)
            ? responseText.trim().slice(0, 1000)
            : "";
        const message = payload.error || payload.message || plainText
            || `The server rejected the upload (${response.status} ${response.statusText || "Request failed"}).`;
        const requestError = new Error(message);
        requestError.status = response.status;
        throw requestError;
    }
    return payload;
}

function setUploadError(element, message = "") {
    element.textContent = message;
    element.hidden = !message;
}

function referenceTypeErrorMessage(error, usesVideo) {
    const choices = (error.message.split(":").pop() || "").trim();
    const staleVideoBackend = usesVideo
        && /Reference type must be one of:/i.test(error.message)
        && !/\bvideo\b/i.test(choices);
    return staleVideoBackend
        ? "The Video reference type is installed but the ComfyUI backend is still running the previous version. Restart ComfyUI, then retry."
        : error.message;
}

async function loadRecords() {
    try {
        const payload = await request(apiRoot);
        state.records = payload.records;
        state.categories = Array.isArray(payload.categories)
            ? payload.categories
            : state.records.map((record) => record.category || "other");
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
        && [record.tag, record.category, normalizedReferenceType(record), record.image_description, record.audio_description, record.video_description]
            .some((value) => (value || "").toLowerCase().includes(query)));
    elements["library-count"].textContent = `${state.records.length} managed reference${state.records.length === 1 ? "" : "s"}`;
    elements.records.replaceChildren(...groupedRecordCards(records));
    elements["empty-state"].hidden = records.length !== 0;
}

function matchesMediaFilter(record, media) {
    if (media === "paired") return record.has_image && record.has_audio;
    if (media === "image") return record.has_image && !record.has_audio && !record.has_video;
    if (media === "audio") return record.has_audio && !record.has_image && !record.has_video;
    if (media === "video_audio") return record.has_video && record.has_video_audio;
    if (media === "video") return record.has_video && !record.has_video_audio;
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
        ...categoryPriority,
        ...state.categories,
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

function updateEditorMediaVisibility() {
    const selected = elements["reference-type"].value;
    const permitted = selected ? allowedMedia(selected) : [];
    for (const kind of ["image", "audio", "video"]) {
        elements[`${kind}-fields`].hidden = !permitted.includes(kind);
    }
}

function recordCard(record) {
    const card = document.createElement("article");
    card.className = "record-card";
    const preview = document.createElement("div");
    preview.className = "record-preview";
    if (record.has_video) {
        const video = document.createElement("video");
        video.src = `${record.video_url}?v=${encodeURIComponent(record.updated_at || "")}`;
        video.controls = true;
        video.preload = "metadata";
        preview.append(video);
    } else if (record.has_image) {
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
    if (record.has_video) badges.append(badge("Video", "video"));
    if (record.has_video_audio) badges.append(badge("Video audio", "audio"));
    title.append(code);
    if (record.has_audio || record.has_video_audio || record.audio_description) title.append(voiceCode);
    title.append(badges);

    const description = document.createElement("div");
    description.className = "description";
    description.textContent = [record.image_description, record.audio_description, record.video_description].filter(Boolean).join(" / ") || "No description";
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
    if (record.has_audio || record.has_video_audio || record.audio_description) actions.append(copyVoice);
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
        video: "Videos",
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
    setUploadError(elements["import-error"]);
    const groups = new Map(state.drafts.map((draft) => [draft.key, draft]));
    for (const file of files) {
        const kind = mediaKind(file);
        if (!kind) continue;
        const key = stem(file.name).toLowerCase();
        const draft = groups.get(key) || {
            key,
            tag: tagFromName(file.name),
            category: "other",
            reference_type: "",
            image_description: "",
            audio_description: "",
            video_description: "",
            image: null,
            audio: null,
            video: null,
        };
        if (draft[kind] && draft[kind] !== file) releaseDraftPreview(draft, kind);
        draft[kind] = file;
        delete draft.error;
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
        tagInput.addEventListener("input", () => { draft.tag = tagInput.value.trim(); });
        tagInput.addEventListener("blur", () => {
            draft.tag = normalizeTag(tagInput.value);
            tagInput.value = draft.tag;
        });
        tagLabel.append(tagInput);
        const categoryLabelElement = document.createElement("label");
        categoryLabelElement.textContent = "Category";
        categoryLabelElement.append(draftCategorySelect(draft));
        const typeLabel = document.createElement("label");
        typeLabel.textContent = "Reference type";
        const typeSelect = document.createElement("select");
        const supportedTypes = supportedReferenceTypes(draft);
        if (!supportedTypes.includes(draft.reference_type)) draft.reference_type = "";
        if (!draft.reference_type && supportedTypes.length === 1) {
            draft.reference_type = supportedTypes[0];
        }
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Select reference type...";
        placeholder.disabled = true;
        typeSelect.append(placeholder, ...supportedTypes.map((referenceType) => {
            const option = document.createElement("option");
            option.value = referenceType;
            option.textContent = referenceTypeLabel(referenceType);
            return option;
        }));
        typeSelect.value = draft.reference_type;
        typeSelect.addEventListener("change", () => {
            draft.reference_type = typeSelect.value;
            renderDrafts();
        });
        typeLabel.append(typeSelect);
        row.append(
            draftPreview(draft),
            tagLabel,
            categoryLabelElement,
            typeLabel,
            draftDescriptions(draft),
            draftMediaSummary(draft),
        );
        if (draft.error) {
            const error = document.createElement("div");
            error.className = "draft-error";
            error.setAttribute("role", "alert");
            error.textContent = `Upload failed: ${draft.error}`;
            row.append(error);
        }
        row.dataset.index = index;
        return row;
    }));
    const hasDrafts = state.drafts.length > 0;
    elements.drafts.hidden = !hasDrafts;
    elements["draft-actions"].hidden = !hasDrafts;
    elements["clear-drafts"].hidden = !hasDrafts;
    elements["draft-summary"].textContent = `${state.drafts.length} reference draft${state.drafts.length === 1 ? "" : "s"}`;
}

function draftDescriptions(draft) {
    const group = document.createElement("div");
    group.className = "draft-description-group";
    const labels = {
        image: "Image description",
        audio: draft.reference_type === "character" ? "Voice description" : "Audio description",
        video: "Video description",
    };
    const placeholders = {
        image: "Describe the visual reference",
        audio: draft.reference_type === "character" ? "Describe the character's voice" : "Describe the sound",
        video: "Describe the video reference",
    };
    const descriptionKinds = draft.reference_type
        ? allowedMedia(draft.reference_type)
        : presentMedia(draft);
    for (const kind of descriptionKinds) {
        const label = document.createElement("label");
        label.className = "draft-description";
        label.textContent = labels[kind];
        const description = document.createElement("textarea");
        description.rows = 2;
        description.placeholder = placeholders[kind];
        description.value = draft[`${kind}_description`] || "";
        description.addEventListener("input", () => {
            draft[`${kind}_description`] = description.value;
        });
        label.append(description);
        group.append(label);
    }
    return group;
}

function draftCategorySelect(draft) {
    const select = document.createElement("select");
    const categories = libraryCategories(draft.category);
    select.append(...categories.map((category) => {
        const option = document.createElement("option");
        option.value = category;
        option.textContent = categoryLabel(category);
        return option;
    }));
    const create = document.createElement("option");
    create.value = "__new__";
    create.textContent = "Create new category...";
    select.append(create);
    select.value = categories.includes(draft.category) ? draft.category : "other";
    select.addEventListener("change", () => {
        if (select.value !== "__new__") {
            draft.category = select.value;
            return;
        }
        const entered = window.prompt("New category name:", "");
        const category = normalizeCategory(entered);
        if (!category) {
            select.value = draft.category;
            return;
        }
        draft.category = category;
        if (!state.categories.includes(category)) state.categories.push(category);
        renderDrafts();
    });
    return select;
}

function draftObjectUrl(draft, kind, file) {
    draft.previewUrls ||= {};
    const current = draft.previewUrls[kind];
    if (current?.file === file) return current.url;
    if (current?.url) URL.revokeObjectURL(current.url);
    const url = URL.createObjectURL(file);
    draft.previewUrls[kind] = { file, url };
    return url;
}

function releaseDraftPreview(draft, kind = null) {
    if (draft.previewPlayer) {
        draft.previewPlayer.pause();
        draft.previewPlayer = null;
    }
    const kinds = kind ? [kind] : Object.keys(draft.previewUrls || {});
    for (const mediaKindName of kinds) {
        const current = draft.previewUrls?.[mediaKindName];
        if (current?.url) URL.revokeObjectURL(current.url);
        if (draft.previewUrls) delete draft.previewUrls[mediaKindName];
    }
}

function draftPreview(draft) {
    if (draft.previewPlayer) {
        draft.previewPlayer.pause();
        draft.previewPlayer = null;
    }
    const preview = document.createElement("div");
    preview.className = "draft-preview";
    const permitted = allowedMedia(draft.reference_type);
    const previewKind = permitted.find((kind) => draft[kind])
        || ["video", "image", "audio"].find((kind) => draft[kind]);
    if (previewKind === "video") {
        const video = document.createElement("video");
        video.src = draftObjectUrl(draft, "video", draft.video);
        video.muted = true;
        video.playsInline = true;
        video.preload = "metadata";
        video.addEventListener("loadedmetadata", () => {
            if (Number.isFinite(video.duration) && video.duration > 0) {
                video.currentTime = Math.min(0.05, video.duration / 2);
            }
        }, { once: true });
        preview.title = `Video: ${draft.video.name}`;
        preview.append(video);
    } else if (previewKind === "image") {
        const image = document.createElement("img");
        image.src = draftObjectUrl(draft, "image", draft.image);
        image.alt = draft.tag || draft.image.name;
        preview.title = `Image: ${draft.image.name}`;
        preview.append(image);
    } else if (previewKind === "audio") {
        const wrapper = document.createElement("div");
        wrapper.className = "draft-audio-preview";
        const icon = document.createElement("span");
        icon.textContent = "♫";
        const play = document.createElement("button");
        play.type = "button";
        play.className = "secondary";
        play.textContent = "Play audio";
        const audio = document.createElement("audio");
        audio.src = draftObjectUrl(draft, "audio", draft.audio);
        audio.preload = "metadata";
        draft.previewPlayer = audio;
        play.addEventListener("click", async () => {
            if (audio.paused) {
                try {
                    await audio.play();
                    play.textContent = "Pause";
                } catch (error) {
                    toast(`Could not preview ${draft.audio.name}.`, true);
                }
            } else {
                audio.pause();
                play.textContent = "Play audio";
            }
        });
        audio.addEventListener("ended", () => { play.textContent = "Play audio"; });
        wrapper.append(icon, play, audio);
        preview.title = `Audio: ${draft.audio.name}`;
        preview.append(wrapper);
    }
    return preview;
}

function draftMediaSummary(draft) {
    const element = document.createElement("div");
    element.className = "draft-media";
    const permitted = draft.reference_type
        ? allowedMedia(draft.reference_type)
        : ["image", "audio", "video"];
    for (const [kind, label, file] of [["image", "Image", draft.image], ["audio", "Audio", draft.audio], ["video", "Video", draft.video]]) {
        if (draft.reference_type && !permitted.includes(kind)) continue;
        const line = document.createElement("div");
        if (file && !permitted.includes(kind)) line.className = "draft-media-ignored";
        const strong = document.createElement("strong");
        strong.textContent = `${label}: `;
        const status = file
            ? `${file.name}${permitted.includes(kind) ? "" : " (not imported for this type)"}`
            : "None";
        line.append(strong, document.createTextNode(status));
        if (kind === "audio" && draft.image
            && (!draft.reference_type || ["character", "object"].includes(draft.reference_type))) {
            line.append(draftAudioUpload(draft));
        }
        element.append(line);
    }
    return element;
}

function draftAudioUpload(draft) {
    const label = document.createElement("label");
    label.className = "draft-upload secondary";
    label.textContent = draft.audio ? "↻ Replace Audio Track" : "+ Add Audio Track";
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "audio/*,.m4a,.opus,.flac";
    input.addEventListener("change", () => {
        const file = input.files[0];
        if (!file) return;
        releaseDraftPreview(draft, "audio");
        draft.audio = file;
        if (!supportedReferenceTypes(draft).includes(draft.reference_type)) {
            draft.reference_type = "";
        }
        renderDrafts();
    });
    label.append(input);
    return label;
}

async function importDrafts() {
    setUploadError(elements["import-error"]);
    state.drafts.forEach((draft) => {
        draft.tag = normalizeTag(draft.tag);
        delete draft.error;
    });
    const rejectImport = (message, draft = null) => {
        if (draft) draft.error = message;
        setUploadError(elements["import-error"], message);
        renderDrafts();
        toast(message, true);
    };
    const tags = state.drafts.map((draft) => draft.tag);
    if (tags.some((tag) => !/^[A-Za-z0-9_-]+$/.test(tag))) return rejectImport("Every draft needs a valid tag.");
    if (state.drafts.some((draft) => !/^[A-Za-z0-9_-]+$/.test(draft.category))) return rejectImport("Every draft needs a valid category.");
    const missingType = state.drafts.find((draft) => !assignableReferenceTypes.includes(draft.reference_type));
    if (missingType) return rejectImport(`Choose a reference type for {${missingType.tag}}.`, missingType);
    const missingMedia = state.drafts.find(
        (draft) => !allowedMedia(draft.reference_type).some((kind) => draft[kind]),
    );
    if (missingMedia) {
        return rejectImport(
            `{${missingMedia.tag}} needs media allowed for ${referenceTypeLabel(missingMedia.reference_type)}.`,
            missingMedia,
        );
    }
    if (new Set(tags).size !== tags.length) return rejectImport("Draft tags must be unique.");
    elements["import-drafts"].disabled = true;
    const importedDrafts = [];
    try {
        for (const draft of state.drafts) {
            const data = new FormData();
            data.append("tag", draft.tag);
            data.append("category", draft.category);
            data.append("reference_type", draft.reference_type);
            const permitted = allowedMedia(draft.reference_type);
            if (permitted.includes("image") && draft.image) {
                data.append("image_description", (draft.image_description || "").trim());
                data.append("image", draft.image);
            }
            if (permitted.includes("audio") && draft.audio) {
                data.append("audio_description", (draft.audio_description || "").trim());
                data.append("audio", draft.audio);
            }
            if (permitted.includes("video") && draft.video) {
                data.append("video_description", (draft.video_description || "").trim());
                data.append("video", draft.video);
            }
            try {
                await request(apiRoot, { method: "POST", body: data });
                importedDrafts.push(draft);
            } catch (error) {
                const message = referenceTypeErrorMessage(error, draft.reference_type === "video");
                for (const imported of importedDrafts) releaseDraftPreview(imported);
                state.drafts = state.drafts.filter((item) => !importedDrafts.includes(item));
                rejectImport(`Could not upload {${draft.tag}}: ${message}`, draft);
                await loadRecords();
                return;
            }
        }
        const count = state.drafts.length;
        clearDrafts();
        await loadRecords();
        toast(`Imported ${count} reference${count === 1 ? "" : "s"}.`);
    } finally {
        elements["import-drafts"].disabled = false;
    }
}

function clearDrafts() {
    state.drafts.forEach((draft) => releaseDraftPreview(draft));
    state.drafts = [];
    elements["bulk-files"].value = "";
    setUploadError(elements["import-error"]);
    renderDrafts();
}

function openEditor(record = null) {
    elements["record-form"].reset();
    setUploadError(elements["record-error"]);
    elements["record-id"].value = record?.id || "";
    elements["dialog-title"].textContent = record ? "Edit reference" : "Add reference";
    elements.tag.value = record?.tag || "";
    renderCategoryChoices(record?.category || "other");
    renderEditorReferenceTypes(record);
    updateEditorMediaVisibility();
    elements["image-description"].value = record?.image_description || "";
    elements["audio-description"].value = record?.audio_description || "";
    elements["video-description"].value = record?.video_description || "";
    elements["remove-image-row"].hidden = !record?.has_image;
    elements["remove-audio-row"].hidden = !record?.has_audio;
    elements["remove-video-row"].hidden = !record?.has_video;
    elements["record-dialog"].showModal();
}

function renderEditorReferenceTypes(record = null) {
    const selected = record ? normalizedReferenceType(record) : "";
    const supported = record ? supportedReferenceTypes(record) : [...assignableReferenceTypes];
    if (record && selected !== "uncategorized" && !supported.includes(selected)) {
        supported.unshift(selected);
    }
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select reference type...";
    placeholder.disabled = true;
    const options = supported.map((referenceType) => {
        const option = document.createElement("option");
        option.value = referenceType;
        option.textContent = referenceTypeLabel(referenceType);
        return option;
    });
    if (selected === "uncategorized") {
        const legacy = document.createElement("option");
        legacy.value = "uncategorized";
        legacy.textContent = "Uncategorized (legacy)";
        legacy.hidden = true;
        options.push(legacy);
    }
    elements["reference-type"].replaceChildren(placeholder, ...options);
    elements["reference-type"].value = selected;
}

async function saveRecord(event) {
    event.preventDefault();
    setUploadError(elements["record-error"]);
    const rejectRecord = (message) => {
        setUploadError(elements["record-error"], message);
        toast(message, true);
    };
    const tag = normalizeTag(elements.tag.value);
    if (!tag) return rejectRecord("Enter a tag containing at least one letter or number.");
    elements.tag.value = tag;
    const category = selectedCategory();
    if (!/^[A-Za-z0-9_-]+$/.test(category)) return rejectRecord("Enter a valid category.");
    const recordId = elements["record-id"].value;
    const selectedReferenceType = elements["reference-type"].value;
    const permitted = allowedMedia(selectedReferenceType);
    const hasExistingOrNewMedia = permitted.some((kind) => {
        const file = elements[`${kind}-file`].files[0];
        const existing = recordId
            && !elements[`remove-${kind}-row`].hidden
            && !elements[`remove-${kind}`].checked;
        return Boolean(file || existing);
    });
    if (!hasExistingOrNewMedia) {
        return rejectRecord(`${referenceTypeLabel(selectedReferenceType)} needs an allowed media file.`);
    }
    const data = new FormData();
    data.append("tag", tag);
    data.append("category", category);
    data.append("reference_type", selectedReferenceType);
    data.append("image_description", permitted.includes("image") ? elements["image-description"].value.trim() : "");
    data.append("audio_description", permitted.includes("audio") ? elements["audio-description"].value.trim() : "");
    data.append("video_description", permitted.includes("video") ? elements["video-description"].value.trim() : "");
    for (const kind of ["image", "audio", "video"]) {
        const allowed = permitted.includes(kind);
        const file = elements[`${kind}-file`].files[0];
        if (allowed && file) data.append(kind, file);
        data.append(`remove_${kind}`, String(!allowed || elements[`remove-${kind}`].checked));
    }
    elements["save-record"].disabled = true;
    try {
        const payload = await request(recordId ? `${apiRoot}/${recordId}` : apiRoot, {
            method: recordId ? "PUT" : "POST",
            body: data,
        });
        const savedReferenceType = normalizedReferenceType(payload.record);
        if (savedReferenceType !== selectedReferenceType) {
            throw new Error(
                `The server returned ${referenceTypeLabel(savedReferenceType)} instead of `
                + `${referenceTypeLabel(selectedReferenceType)}. Reload ComfyUI before trying again.`,
            );
        }
        elements["record-dialog"].close();
        await loadRecords();
        const action = recordId ? "updated" : "added";
        toast(`Reference ${action} as ${referenceTypeLabel(savedReferenceType)}.`);
    } catch (error) {
        rejectRecord(referenceTypeErrorMessage(error, selectedReferenceType === "video"));
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
    if (record.has_audio || record.has_video_audio || record.audio_description) {
        const voiceTag = document.createElement("code");
        voiceTag.className = "voice-tag";
        voiceTag.textContent = `Voice: §${record.tag}§`;
        item.append(voiceTag);
    }
    if (record.image_description) item.append(descriptionLine("Image", record.image_description));
    if (record.audio_description) item.append(descriptionLine("Voice", record.audio_description));
    if (record.video_description) item.append(descriptionLine("Video", record.video_description));
    if (!record.image_description && !record.audio_description && !record.video_description) item.append(descriptionLine("Description", "None"));
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
                if (record.has_audio || record.has_video_audio || record.audio_description) lines.push(`Voice tag: §${record.tag}§`);
                if (record.image_description) lines.push(`Image: ${record.image_description}`);
                if (record.audio_description) lines.push(`Voice: ${record.audio_description}`);
                if (record.video_description) lines.push(`Video: ${record.video_description}`);
                if (!record.image_description && !record.audio_description && !record.video_description) lines.push("Description: None");
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
elements.tag.addEventListener("blur", () => {
    const normalized = normalizeTag(elements.tag.value);
    if (normalized) elements.tag.value = normalized;
});
elements.category.addEventListener("change", () => {
    const creating = elements.category.value === "__new__";
    elements["new-category-row"].hidden = !creating;
    elements["new-category"].required = creating;
    if (creating) elements["new-category"].focus();
});
elements["reference-type"].addEventListener("change", () => {
    updateEditorMediaVisibility();
    if (!elements["record-id"].value) {
        renderCategoryChoices(suggestedCategory(elements["reference-type"].value));
    }
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
