// Shared Reference creator presentation for every library tab.
const categoryPriority=["character","narrator","location","voice","object","style","other"];
const referenceTypes=["character","location","object","music","video","uncategorized"];
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

function selectedGroups(selectedRecords) {
    const groups = new Map();
    for (const record of selectedRecords) {
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

export function renderReferenceGuide(records, elements) {
    const groups = selectedGroups(records);
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
    if (!record.is_refmod || record.has_visual) item.append(tag);
    if (record.built_in) {
        const voiceTag = document.createElement("code");
        voiceTag.className = "voice-tag";
        voiceTag.textContent = `Voice: \u00a7${record.tag}\u00a7`;
        item.append(voiceTag);
        item.append(descriptionLine("Portrayal", portrayalText(record)));
        if (record.has_image) item.append(descriptionLine("Image", "Attached"));
        return item;
    }
    if (record.has_audio || record.voice_source === "refmod" || record.has_video_audio || record.audio_description) {
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

export function referenceGuideText(records) {
    return selectedGroups(records).map(([category, typeGroups]) => {
        const lines = [categoryHeading(category).toUpperCase()];
        for (const [referenceType, records] of typeGroups) {
            lines.push("", referenceTypeHeading(referenceType).toUpperCase());
            for (const record of records) {
                if (!record.is_refmod || record.has_visual) lines.push(`{${record.tag}}`);
                if (record.built_in) {
                    lines.push(`Voice tag: \u00a7${record.tag}\u00a7`);
                    lines.push(`Portrayal: ${portrayalText(record)}`);
                    if (record.has_image) lines.push("Image: Attached");
                    lines.push("");
                    continue;
                }
                if (record.has_audio || record.voice_source === "refmod" || record.has_video_audio || record.audio_description) lines.push(`Voice tag: §${record.tag}§`);
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

function portrayalText(record) {
    const playedBy = record.actor ? `Played by ${record.actor}` : "Actor not listed";
    return record.franchise ? `${playedBy} | ${record.franchise}` : playedBy;
}

