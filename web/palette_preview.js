import { api } from "../../scripts/api.js";

export function previewPrompt(output, nodeId, frame) {
    const source = output[String(nodeId)];
    if (!source?.inputs?.image) throw new Error("Connect an image or video frame batch first.");
    const selected = {...output, [String(nodeId)]: {
        class_type: "SkebaPaletteFramePreview", inputs: {image: source.inputs.image, preview_frame: frame},
    }};
    const ancestors = {};
    const collect = id => {
        if (ancestors[id]) return;
        if (!selected[id]) throw new Error("Cannot resolve preview input in this graph.");
        ancestors[id] = selected[id];
        for (const value of Object.values(selected[id].inputs)) {
            if (Array.isArray(value) && value.length === 2 && typeof value[1] === "number") collect(String(value[0]));
        }
    };
    collect(String(nodeId));
    return ancestors;
}

export function attachPreview(app, node, root, rows, refresh) {
    const frame = node.widgets.find(w => w.name === "preview_frame");
    const mode = node.widgets.find(w => w.name === "sampling_mode");
    const button = document.createElement("button");
    button.textContent = "Preview / Pick Colors";
    const status = document.createElement("div");
    status.style.cssText = "font-size:12px;white-space:normal;";
    status.textContent = "Preview queues the input branch only. Pick colors, then run quantization.";
    const image = document.createElement("img");
    image.alt = "Source frame for palette sampling";
    image.style.cssText = "display:none;width:100%;height:280px;object-fit:contain;cursor:crosshair;";
    root.append(button, status, image);
    let preview = null;
    let active = null;
    let generation = 0;
    const updateButtons = () => rows.forEach((row, i) => {
        row.pick.textContent = active === i ? "PICKING..." : "Pick";
    });
    rows.forEach((row, i) => row.pick.addEventListener("click", () => {
        active = active === i ? null : i;
        updateButtons();
        status.textContent = preview ? `Click the preview for Color ${i + 1}.` : "Click Preview / Pick Colors to load a frame first.";
    }));
    const invalidate = () => {
        generation++;
        preview = null;
        image.style.display = "none";
        status.textContent = "Frame changed. Click Preview / Pick Colors to refresh.";
        refresh();
    };
    const configured = node.onConfigure;
    node.onConfigure = function (...args) {
        if (!Number.isFinite(frame.value)) frame.value = 0;
        if (!["Exact Pixel", "3x3 Average", "5x5 Average"].includes(mode.value)) mode.value = "3x3 Average";
        const result = configured?.apply(this, args);
        invalidate();
        return result;
    };
    const frameChanged = frame.callback;
    frame.callback = function (...args) { frameChanged?.apply(this, args); invalidate(); };
    button.addEventListener("click", async () => {
        button.disabled = true;
        invalidate();
        try {
            const graph = await app.graphToPrompt();
            const output = previewPrompt(graph.output, node.id, Number(frame.value));
            await api.queuePrompt(0, {output, workflow: graph.workflow});
            status.textContent = "Preview queued; waiting for the input frame.";
        } catch (error) {
            status.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    });
    const executed = node.onExecuted;
    node.onExecuted = function (message) {
        const result = executed?.apply(this, arguments);
        const next = message.palette_preview?.[0];
        if (next) {
            preview = next;
            generation++;
            frame.value = next.frame;
            image.src = api.apiURL(`/view?${new URLSearchParams({filename: next.filename, subfolder: next.subfolder, type: next.type})}`);
            image.style.display = "block";
            status.textContent = `Frame ${next.frame} of ${next.frames} (${next.width} x ${next.height}). Select Pick, then click the image.`;
            refresh();
        }
        return result;
    };
    image.addEventListener("click", async event => {
        if (!preview || active === null || rows[active].row.style.display === "none") return;
        // Account for object-fit letterboxing, then map to source-space UV.
        const rect = image.getBoundingClientRect();
        const scale = Math.min(rect.width / preview.width, rect.height / preview.height);
        const width = preview.width * scale, height = preview.height * scale;
        const x = event.clientX - rect.left - (rect.width - width) / 2;
        const y = event.clientY - rect.top - (rect.height - height) / 2;
        if (x < 0 || y < 0 || x > width || y > height) return;
        const slot = active, version = generation;
        try {
            const response = await api.fetchApi("/api/skeba-palette/sample", {
                method: "POST", headers: {"Content-Type": "application/json"},
                body: JSON.stringify({token: preview.token, u: x / width, v: y / height, sampling_mode: mode.value}),
            });
            const sample = await response.json();
            if (!response.ok) throw new Error(sample.error || "Sampling failed.");
            if (version !== generation || active !== slot) return;
            rows[slot].commit(sample.hex);
            status.textContent = `X ${sample.x}, Y ${sample.y} | RGB ${sample.rgb.join(", ")} | ${sample.hex}`;
            active = null;
            updateButtons();
        } catch (error) { status.textContent = error.message; }
    });
    return () => preview ? 360 : 70;
}
