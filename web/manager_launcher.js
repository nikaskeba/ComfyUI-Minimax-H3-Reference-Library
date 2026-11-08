import { app } from "../../../scripts/app.js";

const BUTTON_ID = "skeba-manager-launcher";
const COMMAND_ID = "Comfy.Manager.Menu.ToggleVisibility";

function visibleManagerButton() {
    return [...document.querySelectorAll("button")].some((button) => {
        if (button.id === BUTTON_ID || button.textContent.trim() !== "Manager") return false;
        const rect = button.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && rect.right > 0 && rect.bottom > 0 &&
            rect.left < window.innerWidth && rect.top < window.innerHeight &&
            getComputedStyle(button).visibility !== "hidden";
    });
}

function updateLauncher() {
    const existing = document.getElementById(BUTTON_ID);
    if (visibleManagerButton()) {
        existing?.remove();
        return;
    }
    if (existing || !document.body) return;
    const button = document.createElement("button");
    button.id = BUTTON_ID;
    button.type = "button";
    button.textContent = "Manager";
    button.title = "Open ComfyUI Manager";
    button.style.cssText = "position:fixed;top:56px;right:16px;z-index:10000;padding:7px 12px;border-radius:8px;background:#242b38;color:#fff;border:1px solid #66758d;cursor:pointer";
    button.onclick = async () => {
        try {
            const command = app.extensionManager?.command;
            if (typeof command?.execute !== "function") throw new Error("Manager command unavailable");
            await command.execute(COMMAND_ID);
        } catch (error) {
            console.error("[Skeba] Could not open ComfyUI Manager", error);
            alert("ComfyUI Manager is not ready. Check that its frontend extension is enabled, then reload ComfyUI.");
        }
    };
    document.body.append(button);
}

app.registerExtension({
    name: "skeba.manager.launcher",
    setup() {
        // Manager may register late or its toolbar button may disappear when
        // ComfyUI switches menus. Recheck without depending on Manager files.
        setTimeout(updateLauncher, 5000);
        setInterval(updateLauncher, 3000);
    },
});
