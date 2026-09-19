export function groupCatalog(rows) {
    const files = new Map();
    for (const row of rows) { if (!files.has(row.file)) files.set(row.file, []); files.get(row.file).push(row); }
    const pairs = new Map();
    for (const [file, entries] of files) {
        if (entries.length !== 1 || entries[0].member != null) continue;
        const match = file.match(/^(.*)_(visual|video|audio)\.safetensors$/i);
        if (!match) continue;
        const key = match[1]; if (!pairs.has(key)) pairs.set(key, []); pairs.get(key).push(file);
    }
    const combined = new Map();
    for (const [key, names] of pairs) {
        const entries = names.flatMap(name => files.get(name));
        if (entries.some(row => row.kind === "audio") && entries.some(row => ["image", "video"].includes(row.kind)))
            for (const name of names) combined.set(name, key);
    }
    const groups = new Map();
    for (const [file, entries] of files) {
        const key = combined.get(file) || file;
        if (!groups.has(key)) groups.set(key, {key, rows: [], files: []});
        groups.get(key).rows.push(...entries); groups.get(key).files.push(file);
    }
    return [...groups.values()].map(group => {
        const visual = group.rows.find(row => row.kind === "image" || row.kind === "video");
        const audio = group.rows.find(row => row.kind === "audio");
        const primary = visual || audio || group.rows[0];
        const folder = group.files[0].includes("/") ? group.files[0].slice(0, group.files[0].lastIndexOf("/")) : "(root)";
        const name = primary.subject_name || (primary.name || group.key.split("/").pop()).replace(/_(visual|video|audio)$/i, "");
        return {...group, name, folder, visual, audio, primary, paired: group.files.length > 1};
    });
}
