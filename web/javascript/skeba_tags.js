import { app } from "../../../scripts/app.js";

console.info("[skeba_tags] file loaded");

const STORE_KEY = "__skeba_tags";
const META_KEY = "skeba_tags";
const MENU_INJECT_FLAG = "__skeba_tags_menu_injected";
const EXTRA_MENU_INJECT_FLAG = "__skeba_tags_extra_menu_injected";
const CANVAS_MENU_INJECT_FLAG = "__skeba_tags_canvas_menu_injected";
const COLOR_BASE_KEY = "__skeba_color_base";
const BGCOLOR_BASE_KEY = "__skeba_bgcolor_base";

function isLoraGalleryNode(node) {
  const raw = [
    node?.type || "",
    node?.comfyClass || "",
    node?.title || "",
    node?._meta?.title || "",
  ]
    .join(" ")
    .toLowerCase();
  const compact = raw.replace(/[^a-z0-9]/g, "");
  return (
    raw.includes("local lora gallery") ||
    raw.includes("local_lora_gallery") ||
    raw.includes("localloragallery") ||
    compact.includes("localloragallery")
  );
}

function ensureStore(node) {
  node.properties = node.properties || {};
  node.properties[STORE_KEY] = node.properties[STORE_KEY] || { inputs: [], outputs: [] };
  node.properties[STORE_KEY].inputs = node.properties[STORE_KEY].inputs || [];
  node.properties[STORE_KEY].outputs = node.properties[STORE_KEY].outputs || [];
  return node.properties[STORE_KEY];
}

function inputTagToString(tag) {
  const tagName = tag?.name || "input";
  const tagType = (tag?.type || "text").trim() || "text";
  if (tagType === "bypass") {
    return `#by:${tagName}:bypass`;
  }
  if (tagType === "toggle") {
    return `#by:${tagName}:${tag.enabled === false ? "off" : "on"}`;
  }
  let out = `#in:${tagName}:${tagType}`;
  if (tagType === "number") {
    if (tag.min) out += `|min=${tag.min}`;
    if (tag.max) out += `|max=${tag.max}`;
    if (tag.step) out += `|step=${tag.step}`;
  } else if (tagType === "select") {
    out += `|options=${(tag.options || []).join(",")}`;
  } else if (tagType === "combo") {
    out += `|combo:[${(tag.options || []).join(",")}]`;
  } else if (tagType === "lora") {
    if (tag.group) out += `|group=${tag.group}`;
  }
  if (tag.optional) out += "|optional=1";
  return out;
}

function outputTagToString(tag) {
  return `#out:${tag.name}:${tag.type}`;
}

function syncStoreToMeta(node) {
  const store = ensureStore(node);
  node._meta = node._meta || {};
  node._meta[META_KEY] = {
    inputs: store.inputs.map(inputTagToString),
    outputs: store.outputs.map(outputTagToString),
  };
}

function updateNodeVisualTag(node) {
  if (!node) return;
  node.properties = node.properties || {};
  const store = ensureStore(node);
  if (!(COLOR_BASE_KEY in node.properties)) node.properties[COLOR_BASE_KEY] = node.color;
  if (!(BGCOLOR_BASE_KEY in node.properties)) node.properties[BGCOLOR_BASE_KEY] = node.bgcolor;

  if (store.inputs.length) {
    node.color = "#2d6a4f";
  } else if (store.outputs.length) {
    node.color = "#355070";
  } else {
    node.color = node.properties[COLOR_BASE_KEY];
    node.bgcolor = node.properties[BGCOLOR_BASE_KEY];
  }
}

function setSingleInput(node, tag) {
  const store = ensureStore(node);
  store.inputs = tag ? [tag] : [];
  store.outputs = [];
  syncStoreToMeta(node);
  updateNodeVisualTag(node);
  node.setDirtyCanvas?.(true, true);
}

function setSingleOutput(node, tag) {
  const store = ensureStore(node);
  store.outputs = tag ? [tag] : [];
  store.inputs = [];
  syncStoreToMeta(node);
  updateNodeVisualTag(node);
  node.setDirtyCanvas?.(true, true);
}

function clearTags(node) {
  const store = ensureStore(node);
  store.inputs = [];
  store.outputs = [];
  syncStoreToMeta(node);
  updateNodeVisualTag(node);
  node.setDirtyCanvas?.(true, true);
}

function showTags(node) {
  const store = ensureStore(node);
  const bypassLines = store.inputs
    .filter((t) => ["bypass", "toggle"].includes((t?.type || "").trim()))
    .map(inputTagToString);
  const inLines = store.inputs
    .filter((t) => !["bypass", "toggle"].includes((t?.type || "").trim()))
    .map(inputTagToString);
  const outLines = store.outputs.map(outputTagToString);
  alert(
    [
      "Inputs:",
      ...(inLines.length ? inLines : ["(none)"]),
      "",
      "Bypass:",
      ...(bypassLines.length ? bypassLines : ["(none)"]),
      "",
      "Outputs:",
      ...(outLines.length ? outLines : ["(none)"]),
    ].join("\n")
  );
}

function parseOptionsCsv(v) {
  return (v || "").split(",").map((x) => x.trim()).filter(Boolean);
}

function parseInputMeta(rawType) {
  const parts = (rawType || "").split("|");
  const type = (parts[0] || "text").trim() || "text";
  const meta = {};
  for (let i = 1; i < parts.length; i++) {
    const [k, v = ""] = parts[i].split("=");
    const key = (k || "").trim().toLowerCase();
    const val = (v || "").trim().toLowerCase();
    if (key === "optional") {
      meta.optional = val === "1" || val === "true" || val === "yes";
    }
  }
  return { type, meta };
}

function openTagBuilderModal(node, mode, forcedType = null) {
  if (!node) return;
  const isLoraNode = isLoraGalleryNode(node);
  const existing = ensureStore(node);
  const existingTag = mode === "input" ? existing.inputs[0] : existing.outputs[0];
  const isBypassMode = forcedType === "bypass";
  const isToggleMode = forcedType === "toggle";

  const overlay = document.createElement("div");
  overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:999999;display:flex;align-items:center;justify-content:center;";
  const panel = document.createElement("div");
  panel.style.cssText = "width:430px;max-width:92vw;background:#1f2937;color:#e5e7eb;border:1px solid #374151;border-radius:10px;padding:14px;font:13px/1.4 sans-serif;";
  overlay.appendChild(panel);

  const title = document.createElement("div");
  if (isBypassMode || isToggleMode) {
    title.textContent = isToggleMode ? "Skeba Toggle Builder" : "Skeba Bypass Builder";
  } else {
    title.textContent = mode === "input" ? "Skeba Input Builder" : "Skeba Output Builder";
  }
  title.style.cssText = "font-weight:700;margin-bottom:10px;";
  panel.appendChild(title);

  const row = (label, el) => {
    const wrap = document.createElement("div");
    wrap.style.cssText = "margin-bottom:8px;";
    const l = document.createElement("div");
    l.textContent = label;
    l.style.cssText = "margin-bottom:3px;color:#9ca3af;";
    wrap.appendChild(l);
    wrap.appendChild(el);
    panel.appendChild(wrap);
    return wrap;
  };
  const mkInput = (v = "") => {
    const i = document.createElement("input");
    i.value = v;
    i.style.cssText = "width:100%;box-sizing:border-box;padding:6px 8px;background:#111827;border:1px solid #374151;border-radius:6px;color:#e5e7eb;";
    return i;
  };
  const mkSelect = (opts, v = "") => {
    const s = document.createElement("select");
    s.style.cssText = "width:100%;box-sizing:border-box;padding:6px 8px;background:#111827;border:1px solid #374151;border-radius:6px;color:#e5e7eb;";
    for (const o of opts) {
      const op = document.createElement("option");
      op.value = o.value;
      op.textContent = o.label;
      s.appendChild(op);
    }
    if (v) s.value = v;
    return s;
  };
  const mkCheckbox = (checked = false) => {
    const i = document.createElement("input");
    i.type = "checkbox";
    i.checked = !!checked;
    i.style.cssText = "width:16px;height:16px;accent-color:#1d4ed8;cursor:pointer;";
    return i;
  };

  const typeOpts =
    mode === "input"
      ? (isLoraNode
          ? [{ value: "lora", label: "Lora" }]
          : [
              { value: "text", label: "Text" },
              { value: "number", label: "Number" },
              { value: "mask", label: "Mask" },
              { value: "select", label: "Select" },
              { value: "combo", label: "Combo" },
              { value: "image", label: "Image" },
              { value: "audio", label: "Audio" },
              { value: "video", label: "Video" },
            ])
      : [
          { value: "text", label: "Text" },
          { value: "image", label: "Image" },
          { value: "audio", label: "Audio" },
          { value: "video", label: "Video" },
        ];

  const typeSelect = mkSelect(typeOpts, forcedType || existingTag?.type || typeOpts[0].value);
  const typeRow = row("Type", typeSelect);
  const presetSelect = mkSelect(
    [
      { value: "custom", label: "Custom" },
      { value: "seed", label: "Seed" },
      { value: "height", label: "Height" },
      { value: "width", label: "Width" },
    ],
    "custom"
  );
  const presetRow = row("Preset", presetSelect);
  const nameInput = mkInput(existingTag?.name || "");
  const nameRow = row(
    isBypassMode || isToggleMode ? "Bypass Name" : mode === "input" ? "Input Name" : "Output Name",
    nameInput
  );
  const minInput = mkInput(existingTag?.min || "");
  const maxInput = mkInput(existingTag?.max || "");
  const stepInput = mkInput(existingTag?.step || "");
  const minRow = row("Min (optional)", minInput);
  const maxRow = row("Max (optional)", maxInput);
  const stepRow = row("Step (optional)", stepInput);
  const optionsInput = mkInput((existingTag?.options || []).join(","));
  const optionsRow = row("Options (comma-separated)", optionsInput);
  const groupInput = mkInput(existingTag?.group || "");
  const groupRow = row("Group (optional)", groupInput);
  const optionalInput = mkCheckbox(!!existingTag?.optional);
  const optionalRow = row("Make optional", optionalInput);
  const enabledInput = mkSelect(
    [
      { value: "on", label: "On" },
      { value: "off", label: "Off" },
    ],
    existingTag?.enabled === false ? "off" : "on"
  );
  const enabledRow = row("Default", enabledInput);

  const refresh = () => {
    const t = typeSelect.value;
    presetRow.style.display = mode === "input" && !isLoraNode && t === "number" ? "" : "none";
    minRow.style.display = t === "number" ? "" : "none";
    maxRow.style.display = t === "number" ? "" : "none";
    stepRow.style.display = t === "number" ? "" : "none";
    optionsRow.style.display = t === "select" || t === "combo" ? "" : "none";
    groupRow.style.display = t === "lora" ? "" : "none";
    optionalRow.style.display = mode === "input" && !["bypass", "toggle"].includes(t) ? "" : "none";
    enabledRow.style.display = t === "toggle" ? "" : "none";
    if (t === "lora") {
      nameInput.value = "selection_data";
      nameInput.disabled = true;
    } else {
      nameInput.disabled = false;
    }
    if (t === "mask" && !nameInput.value.trim()) {
      nameInput.value = "mask";
    }
    if (t === "bypass" && !nameInput.value.trim()) {
      nameInput.value = "input_2";
    }
    if (t === "toggle" && !nameInput.value.trim()) {
      nameInput.value = node?.title || node?.type || "toggle";
    }
  };

  presetSelect.addEventListener("change", () => {
    const p = presetSelect.value;
    if (p === "seed") {
      typeSelect.value = "number";
      nameInput.value = "seed";
      minInput.value = "0";
      maxInput.value = "2000000000";
      stepInput.value = "1";
    } else if (p === "width") {
      typeSelect.value = "number";
      nameInput.value = "width";
      minInput.value = "256";
      maxInput.value = "2048";
      stepInput.value = "64";
    } else if (p === "height") {
      typeSelect.value = "number";
      nameInput.value = "height";
      minInput.value = "256";
      maxInput.value = "2048";
      stepInput.value = "64";
    }
    refresh();
  });
  typeSelect.addEventListener("change", refresh);
  refresh();
  if (isBypassMode || isToggleMode) {
    typeRow.style.display = "none";
    typeSelect.value = isToggleMode ? "toggle" : "bypass";
    typeSelect.disabled = true;
    presetRow.style.display = "none";
    minRow.style.display = "none";
    maxRow.style.display = "none";
    stepRow.style.display = "none";
    optionsRow.style.display = "none";
    groupRow.style.display = "none";
    optionalRow.style.display = "none";
    enabledRow.style.display = isToggleMode ? "" : "none";
    if (!nameInput.value.trim()) nameInput.value = isToggleMode ? node?.title || node?.type || "toggle" : "input_2";
  }

  const actions = document.createElement("div");
  actions.style.cssText = "display:flex;justify-content:flex-end;gap:8px;margin-top:10px;";
  const cancelBtn = document.createElement("button");
  cancelBtn.textContent = "Cancel";
  cancelBtn.style.cssText = "padding:6px 10px;border-radius:6px;border:1px solid #4b5563;background:#111827;color:#e5e7eb;cursor:pointer;";
  const saveBtn = document.createElement("button");
  saveBtn.textContent = "Save";
  saveBtn.style.cssText = "padding:6px 10px;border-radius:6px;border:1px solid #2563eb;background:#1d4ed8;color:white;cursor:pointer;";
  actions.appendChild(cancelBtn);
  actions.appendChild(saveBtn);
  panel.appendChild(actions);

  cancelBtn.onclick = () => overlay.remove();
  saveBtn.onclick = () => {
    const type = isBypassMode ? "bypass" : isToggleMode ? "toggle" : typeSelect.value;
    const name = (nameInput.value || "").trim();
    if (!name) {
      alert(type === "text" ? "Text Input Name is required." : "Name is required.");
      return;
    }
    const tag = { name, type };
    if (type === "number") {
      if (minInput.value.trim()) tag.min = minInput.value.trim();
      if (maxInput.value.trim()) tag.max = maxInput.value.trim();
      if (stepInput.value.trim()) tag.step = stepInput.value.trim();
    }
    if (type === "select" || type === "combo") {
      const options = parseOptionsCsv(optionsInput.value);
      if (!options.length) {
        alert("Options are required.");
        return;
      }
      tag.options = options;
    }
    if (type === "lora" && groupInput.value.trim()) tag.group = groupInput.value.trim();
    if (type === "toggle") {
      tag.enabled = enabledInput.value !== "off";
    }
    if (mode === "input" && !["bypass", "toggle"].includes(type)) tag.optional = !!optionalInput.checked;
    if (mode === "input") setSingleInput(node, tag);
    else setSingleOutput(node, tag);
    overlay.remove();
  };

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });
  document.body.appendChild(overlay);
}

function patchNodeBadge(nodeType) {
  const flag = "__skeba_tags_badge_patched";
  if (!nodeType?.prototype || nodeType.prototype[flag]) return;
  nodeType.prototype[flag] = true;

  const original = nodeType.prototype.onDrawForeground;
  nodeType.prototype.onDrawForeground = function (ctx) {
    const r = original?.apply?.(this, arguments);
    const store = this?.properties?.[STORE_KEY];
    const inCount = store?.inputs?.length || 0;
    const outCount = store?.outputs?.length || 0;
    if (!inCount && !outCount) return r;

    const labels = [];
    if (inCount) labels.push("IN");
    if (outCount) labels.push("OUT");
    const titleH = Number(LiteGraph?.NODE_TITLE_HEIGHT) || 24;
    const y = -titleH + 4;
    const xPad = 8;
    const drawRounded = (x, y, w, h, radius) => {
      ctx.beginPath();
      if (typeof ctx.roundRect === "function") ctx.roundRect(x, y, w, h, radius);
      else ctx.rect(x, y, w, h);
      ctx.fill();
    };

    ctx.save();
    ctx.font = "bold 12px sans-serif";
    ctx.textBaseline = "middle";
    let x = this.size[0] - 8;
    for (let i = labels.length - 1; i >= 0; i--) {
      const t = labels[i];
      const w = Math.ceil(ctx.measureText(t).width) + xPad * 2;
      x -= w;
      ctx.fillStyle = t === "IN" ? "#2d6a4f" : "#355070";
      drawRounded(x, y, w, 16, 6);
      ctx.fillStyle = "#ffffff";
      ctx.fillText(t, x + xPad, y + 8);
      x -= 6;
    }

    if (this.mouseOver) {
      const lines = [
        ...(store.inputs || []).map(inputTagToString),
        ...(store.outputs || []).map(outputTagToString),
      ];
      if (lines.length) {
        const lineH = 14;
        const pad = 6;
        const tipW = Math.ceil(Math.max(...lines.map((line) => ctx.measureText(line).width))) + pad * 2;
        const tipH = lines.length * lineH + pad * 2;
        const tipX = 8;
        const tipY = y - tipH - 6;
        ctx.fillStyle = "rgba(0,0,0,0.85)";
        drawRounded(tipX, tipY, tipW, tipH, 6);
        ctx.fillStyle = "#e6edf3";
        for (let i = 0; i < lines.length; i++) {
          ctx.fillText(lines[i], tipX + pad, tipY + pad + i * lineH + lineH / 2);
        }
      }
    }
    ctx.restore();
    return r;
  };
}

function patchNodeSerialization(nodeType) {
  const flag = "__skeba_tags_serialize_patched";
  if (!nodeType?.prototype || nodeType.prototype[flag]) return;
  nodeType.prototype[flag] = true;

  const originalOnSerialize = nodeType.prototype.onSerialize;
  nodeType.prototype.onSerialize = function (o) {
    const r = originalOnSerialize?.apply?.(this, arguments);
    const store = ensureStore(this);
    o._meta = o._meta || {};
    o._meta[META_KEY] = {
      inputs: store.inputs.map(inputTagToString),
      outputs: store.outputs.map(outputTagToString),
    };
    return r;
  };

  const originalOnConfigure = nodeType.prototype.onConfigure;
  nodeType.prototype.onConfigure = function (o) {
    const r = originalOnConfigure?.apply?.(this, arguments);
    const meta = o?._meta?.[META_KEY];
    if (meta && typeof meta === "object") {
      const store = ensureStore(this);
      if ((!store.inputs || !store.inputs.length) && Array.isArray(meta.inputs)) {
        const inputTags = meta.inputs
          .filter(
            (x) =>
              typeof x === "string" &&
              (x.startsWith("#in:") || x.startsWith("#by:"))
          )
          .map((x) => {
            const p = x.split(":");
            const isBypass = x.startsWith("#by:");
            const rawType = p[2] || "text";
            const parsed = parseInputMeta(p[2] || "text");
            return {
              name: p[1] || "input",
              type: isBypass && rawType !== "bypass" ? "toggle" : isBypass ? "bypass" : parsed.type,
              ...(isBypass && rawType !== "bypass" ? { enabled: rawType !== "off" && rawType !== "false" && rawType !== "0" } : {}),
              ...(isBypass ? {} : parsed.meta),
            };
          });
        store.inputs = inputTags;
      }
      if ((!store.outputs || !store.outputs.length) && Array.isArray(meta.outputs)) {
        store.outputs = meta.outputs
          .filter((x) => typeof x === "string" && x.startsWith("#out:"))
          .map((x) => {
            const p = x.split(":");
            return { name: p[1] || "output", type: p[2] || "any" };
          });
      }
    }
    updateNodeVisualTag(this);
    return r;
  };
}

function patchExistingNodeTypes() {
  const nodeTypes = LiteGraph?.registered_node_types;
  if (!nodeTypes || typeof nodeTypes !== "object") return;
  for (const nodeType of Object.values(nodeTypes)) {
    patchNodeBadge(nodeType);
    patchNodeSerialization(nodeType);
  }
}

function patchBaseNodeSerialize() {
  const flag = "__skeba_tags_base_serialize_patched";
  if (typeof LGraphNode === "undefined" || LGraphNode.prototype[flag]) return;
  LGraphNode.prototype[flag] = true;

  const original = LGraphNode.prototype.serialize;
  LGraphNode.prototype.serialize = function () {
    const o = original ? original.apply(this, arguments) : {};
    const store = this?.properties?.[STORE_KEY];
    if (!store) return o;
    const inputs = (store.inputs || []).map(inputTagToString);
    const outputs = (store.outputs || []).map(outputTagToString);
    if (!inputs.length && !outputs.length) return o;
    o._meta = o._meta || {};
    o._meta[META_KEY] = { inputs, outputs };
    return o;
  };
}

function collectTagsByNodeId() {
  const byId = {};

  const visitGraph = (graph, prefix = "") => {
    const nodes = graph?._nodes || [];
    for (const node of nodes) {
      const nodeKey = prefix ? `${prefix}:${node.id}` : String(node.id);
      const store = node?.properties?.[STORE_KEY];
      const inTags = (store?.inputs || []).map(inputTagToString);
      const outTags = (store?.outputs || []).map(outputTagToString);
      if (inTags.length || outTags.length) {
        byId[nodeKey] = { inputs: inTags, outputs: outTags };
      }

      if (node?.subgraph) {
        visitGraph(node.subgraph, nodeKey);
      }
    }
  };

  visitGraph(app?.graph, "");
  return byId;
}

function patchGraphToPrompt() {
  const flag = "__skeba_tags_graph_to_prompt_patched";
  if (!app || app[flag] || typeof app.graphToPrompt !== "function") return;
  app[flag] = true;

  const original = app.graphToPrompt.bind(app);
  app.graphToPrompt = async function () {
    const result = await original(...arguments);
    const tagsByNode = collectTagsByNodeId();
    const promptObj = result?.output || result?.prompt;
    if (promptObj && typeof promptObj === "object") {
      for (const [nodeId, tags] of Object.entries(tagsByNode)) {
        const nodeData = promptObj[nodeId];
        if (!nodeData || typeof nodeData !== "object") continue;
        nodeData._meta = nodeData._meta || {};
        nodeData._meta[META_KEY] = tags;
      }
    }
    return result;
  };
  console.info("[skeba_tags] patched app.graphToPrompt");
}

function buildSkebaMenuOptions(node) {
  const store = node ? ensureStore(node) : { inputs: [], outputs: [] };
  const options = [];

  options.push({
    content: "Input",
    callback: () => openTagBuilderModal(node, "input"),
  });
  options.push({
    content: "Output",
    callback: () => openTagBuilderModal(node, "output"),
  });
  options.push({
    content: "Bypass (legacy)",
    callback: () => openTagBuilderModal(node, "input", "bypass"),
  });
  options.push({
    content: "Bypass Toggle",
    callback: () => openTagBuilderModal(node, "input", "toggle"),
  });
  options.push({
    content: "Clear",
    disabled: !store.inputs.length && !store.outputs.length,
    callback: () => clearTags(node),
  });
  options.push({
    content: "ShowTags",
    callback: () => showTags(node),
  });
  return options;
}

app.registerExtension({
  name: "Comfy.Skeba.tags",
  init() {
    console.info("[skeba_tags] init");
    patchBaseNodeSerialize();
    patchExistingNodeTypes();

    if (typeof LGraphCanvas !== "undefined" && !LGraphCanvas.prototype[MENU_INJECT_FLAG]) {
      LGraphCanvas.prototype[MENU_INJECT_FLAG] = true;
      const original = LGraphCanvas.prototype.getNodeMenuOptions;
      LGraphCanvas.prototype.getNodeMenuOptions = function (node) {
        const options = original ? original.apply(this, arguments) : [];
        return [
          { content: "Skeba Nodes", has_submenu: true, submenu: { options: buildSkebaMenuOptions(node) } },
          null,
          ...options,
        ];
      };
      console.info("[skeba_tags] patched getNodeMenuOptions");
    }

    if (typeof LGraphCanvas !== "undefined" && !LGraphCanvas.prototype[CANVAS_MENU_INJECT_FLAG]) {
      LGraphCanvas.prototype[CANVAS_MENU_INJECT_FLAG] = true;
      const original = LGraphCanvas.prototype.getCanvasMenuOptions;
      LGraphCanvas.prototype.getCanvasMenuOptions = function () {
        const options = original ? original.apply(this, arguments) : [];
        const selected = this?.selected_nodes ? Object.values(this.selected_nodes) : [];
        if (!selected || selected.length !== 1) return options;
        const node = selected[0];
        return [
          { content: "Skeba Nodes", has_submenu: true, submenu: { options: buildSkebaMenuOptions(node) } },
          null,
          ...options,
        ];
      };
      console.info("[skeba_tags] patched getCanvasMenuOptions");
    }

    patchGraphToPrompt();
  },
  async beforeRegisterNodeDef(nodeType) {
    patchNodeBadge(nodeType);
    patchNodeSerialization(nodeType);
    if (!nodeType?.prototype || nodeType.prototype[EXTRA_MENU_INJECT_FLAG]) return;
    nodeType.prototype[EXTRA_MENU_INJECT_FLAG] = true;
    const original = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function (_, options) {
      const res = original ? original.apply(this, arguments) : undefined;
      if (Array.isArray(options)) {
        options.push(null);
        options.push({
          content: "Skeba Nodes",
          has_submenu: true,
          submenu: { options: buildSkebaMenuOptions(this) },
        });
      }
      return res;
    };
  },
});

