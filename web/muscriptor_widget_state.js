export const FIELDS = [
    "model_size", "device", "dtype", "use_sampling", "temperature", "cfg_coef",
    "beam_size", "prelude_forcing", "strict_eos", "filename_prefix", "invalid_notes",
    "audio_path", "instruments", "tempo_override_bpm",
];

const DEFAULTS = [
    "medium", "auto", "auto", false, 1, 1, 1, true, false,
    "Skeba Music/muscriptor_grid", "Skip malformed", "", "", 0,
];

function valid(name, value, instruments) {
    if (name === "model_size") return ["small", "medium", "large"].includes(value);
    if (name === "device") return ["auto", "cpu", "cuda", "mps"].includes(value);
    if (name === "dtype") return ["auto", "float32", "float16", "bfloat16"].includes(value);
    if (["use_sampling", "prelude_forcing", "strict_eos"].includes(name)) return typeof value === "boolean";
    if (["temperature", "cfg_coef"].includes(name)) return typeof value === "number" && Number.isFinite(value) && value >= 0;
    if (name === "beam_size") return Number.isInteger(value) && value >= 1 && value <= 10;
    if (name === "invalid_notes") return ["Skip malformed", "Strict error"].includes(value);
    if (["filename_prefix", "audio_path"].includes(name)) return typeof value === "string";
    if (name === "instruments") {
        return typeof value === "string" && (value === "" || value === "__none__" ||
            value.split(/[\r\n,]+/).every(part => !part.trim() || instruments.includes(part.trim())));
    }
    if (name === "tempo_override_bpm") return typeof value === "number" && Number.isFinite(value) &&
        (value === 0 || (value >= 20 && value <= 400));
    return false;
}

export function restoredValues(serialized, named = {}, instruments = []) {
    const values = Array.isArray(serialized) ? serialized : [];
    let bestShift = 0;
    let bestScore = -Infinity;
    // Earlier schema versions and saved widget layouts can omit leading controls.
    for (let shift = 0; shift <= 3; shift++) {
        let score = 0;
        for (let i = 0; i < Math.min(values.length, FIELDS.length - shift); i++) {
            const field = FIELDS[i + shift];
            score += valid(field, values[i], instruments) ? 2 : -3;
        }
        score -= shift; // Prefer the unchanged layout when scores tie.
        if (score > bestScore) {
            bestScore = score;
            bestShift = shift;
        }
    }
    return FIELDS.map((field, index) => {
        const raw = values[index - bestShift];
        if (index >= bestShift && valid(field, raw, instruments)) return raw;
        if (valid(field, named?.[field], instruments)) return named[field];
        return DEFAULTS[index];
    });
}
