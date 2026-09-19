import { app } from "../../scripts/app.js";
import "./universal_bypass.js";


const openReferenceLibrary = () => {
    window.open(`${window.location.origin}/h3-references`, "_blank");
};

const openBuiltInCharacters = () => {
    window.open(`${window.location.origin}/h3-built-in-references`, "_blank");
};


app.registerExtension({
    name: "H3ReferenceLibrary.Toolbar",
    setup() {
        if (document.getElementById("h3-reference-library-icon-style")) return;
        const style = document.createElement("style");
        style.id = "h3-reference-library-icon-style";
        const iconUrl = new URL("./library-icon.svg", import.meta.url).href;
        style.textContent = `
            .h3-reference-library-icon {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 1.75rem;
                height: 1.75rem;
                flex-shrink: 0;
                background-color: #000;
                border-radius: 6px;
            }
            .h3-reference-library-icon::before {
                content: "";
                display: block;
                width: 1rem;
                height: 1rem;
                background-color: #fff;
                -webkit-mask: url("${iconUrl}") center / contain no-repeat;
                mask: url("${iconUrl}") center / contain no-repeat;
            }
        `;
        document.head.appendChild(style);
    },
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (!["H3TaggedReferencePrompt", "H3BuiltInReference"].includes(nodeData.name)) {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);
            const builtInNode = nodeData.name === "H3BuiltInReference";
            this.addWidget(
                "button",
                builtInNode ? "Open Built-In Characters" : "Open Reference Library",
                null,
                builtInNode ? openBuiltInCharacters : openReferenceLibrary,
            );
            return result;
        };
    },
    actionBarButtons: [
        {
            icon: "h3-reference-library-icon",
            tooltip: "Open H3 Reference Library",
            onClick: openReferenceLibrary,
        },
    ],
});
