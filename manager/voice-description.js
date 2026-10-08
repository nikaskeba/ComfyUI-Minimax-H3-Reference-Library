export async function requestVoiceDescription(form) {
    const response = await fetch("/api/h3-references/voice-description", {method: "POST", body: form});
    if (!(response.headers.get("content-type") || "").includes("json")) throw Error("Restart ComfyUI and refresh to enable voice descriptions.");
    const result = await response.json();
    if (!response.ok) throw Error(result.error || "Voice analysis failed.");
    return result;
}

// getSource supplies a stable key and a read-only analysis operation.
export function voiceDescriptionControl(field, getSource) {
    const element = document.createElement("div");
    const generate = document.createElement("button"), undo = document.createElement("button"), status = document.createElement("span");
    generate.type = undo.type = "button";
    generate.textContent = "Generate voice description";
    undo.textContent = "Undo"; undo.hidden = true;
    status.setAttribute("role", "status");
    element.append(generate, undo, status);
    let busy = false, revision = 0, previous = "", generated = "";
    const changed = () => {revision++; undo.hidden = true;};
    field.addEventListener("input", changed);
    const insert = text => {field.value = text; field.dispatchEvent(new Event("input", {bubbles:true})); field.dispatchEvent(new Event("change", {bubbles:true}));};
    function refresh() {generate.disabled = busy || !getSource();}
    function invalidate() {revision++; status.textContent = ""; undo.hidden = true; refresh();}
    generate.onclick = async () => {
        const source = getSource(); if (!source || busy) return;
        const original = field.value, started = revision;
        busy = true; refresh(); status.textContent = "Analyzing up to 15 seconds…";
        try {
            const result = await source.run(message => {if (element.isConnected && revision === started) status.textContent = message;});
            if (!element.isConnected || started !== revision || original !== field.value || source.key !== getSource()?.key) {
                status.textContent = "Audio or description changed; result was not inserted."; return;
            }
            previous = original; generated = result.description; insert(generated); undo.hidden = false;
            status.textContent = `Analyzed ${result.seconds.toFixed(1)}s. Review and save your description. Accent is not detected.`;
        } catch (error) {if (element.isConnected && started === revision) status.textContent = error.message;}
        finally {busy = false; refresh();}
    };
    undo.onclick = () => {if (field.value === generated) insert(previous); undo.hidden = true; status.textContent = "Previous description restored.";};
    refresh();
    return {element, refresh, invalidate};
}
