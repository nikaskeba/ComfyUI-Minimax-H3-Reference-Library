const app = window.comfyAPI?.app || window.app;
const STORE_KEY = "__skeba_io";
const PATCH_FLAG = "__skeba_io_menu_patched";
const EXTRA_FLAG = "__skeba_io_extra_menu_patched";

console.info("[skeba_io_tags] file loaded");

function ensureStore(node) {
  node.properties = node.properties || {};
  node.properties[STORE_KEY] = node.properties[STORE_KEY] || {};
  return node.properties[STORE_KEY];
}

function setInputTag(node) {
  if (!node) return;
  const existing = node?.properties?.[STORE_KEY]?.input_tag || "";
  const value = window.prompt("Tag as input:", existing || "input");
  if (value == null) return;

  const tag = value.trim();
  const store = ensureStore(node);

  if (!tag) {
    delete store.input_tag;
    return;
  }

  store.input_tag = tag;
}

function buildSkebaMenu(node) {
  return {
    content: "Skeba Nodes",
    has_submenu: true,
    submenu: {
      options: [
        {
          content: "Tag as input",
          callback: () => {
            setInputTag(node);
            app.graph.setDirtyCanvas(true, true);
          },
        },
      ],
    },
  };
}

function patchCanvasMenu() {
  if (typeof LGraphCanvas === "undefined") return false;
  if (LGraphCanvas.prototype[PATCH_FLAG]) return true;
  LGraphCanvas.prototype[PATCH_FLAG] = true;

  const getNodeMenuOptions = LGraphCanvas.prototype.getNodeMenuOptions;
  LGraphCanvas.prototype.getNodeMenuOptions = function (node) {
    const options = getNodeMenuOptions ? getNodeMenuOptions.apply(this, arguments) : [];
    if (node) node.setDirtyCanvas(true, true);
    return [buildSkebaMenu(node), null, ...options];
  };
  console.info("[skeba_io_tags] patched LGraphCanvas.getNodeMenuOptions");
  return true;
}

function patchExtraMenu(nodeType) {
  if (!nodeType?.prototype || nodeType.prototype[EXTRA_FLAG]) return;
  nodeType.prototype[EXTRA_FLAG] = true;
  const original = nodeType.prototype.getExtraMenuOptions;
  nodeType.prototype.getExtraMenuOptions = function (_, options) {
    const res = original ? original.apply(this, arguments) : undefined;
    if (Array.isArray(options)) {
      options.push(null);
      options.push(buildSkebaMenu(this));
    }
    return res;
  };
}

if (!app?.registerExtension) {
  console.warn("[skeba_io_tags] app.registerExtension unavailable");
} else {
  app.registerExtension({
    name: "skeba.io_tags",
    setup() {
      console.info("[skeba_io_tags] setup");
      if (patchCanvasMenu()) return;

      // If LiteGraph isn't ready yet, retry shortly.
      let tries = 0;
      const t = setInterval(() => {
        tries += 1;
        if (patchCanvasMenu() || tries >= 40) {
          clearInterval(t);
          if (tries >= 40) {
            console.warn("[skeba_io_tags] could not patch canvas menu");
          }
        }
      }, 250);
    },
    async beforeRegisterNodeDef(nodeType) {
      patchExtraMenu(nodeType);
    },
  });
}

