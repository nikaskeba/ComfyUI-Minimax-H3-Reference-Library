import { app } from "../../scripts/app.js";


const openReferenceLibrary = () => {
    window.open(`${window.location.origin}/h3-references`, "_blank");
};

const openBuiltInCharacters = () => {
    window.open(`${window.location.origin}/h3-built-in-references`, "_blank");
};


app.registerExtension({
    name: "H3ReferenceLibrary.Toolbar",
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
            icon: "icon-[lucide--library] size-4",
            tooltip: "Open H3 Reference Library",
            onClick: openReferenceLibrary,
        },
    ],
});
