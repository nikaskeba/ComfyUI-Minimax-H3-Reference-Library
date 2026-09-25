class SkebaWorkflowGuide:
    """Workflow documentation; rendering and editing happen in the browser."""

    CATEGORY = "Skeba AI Nodes - Utilities"
    RETURN_TYPES = ()
    FUNCTION = "guide"
    OUTPUT_NODE = False

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"html": ("STRING", {"multiline": True, "default":
            '<h2 style="color:#8dd6ff">Workflow guide</h2>\n'
            '<p>Double-click this guide to edit its HTML.</p>\n'
            '<div style="background:#243b4f;padding:12px;border-left:4px solid #8dd6ff;border-radius:6px">'
            '<strong>Getting started</strong><ol><li>Choose your references.</li>'
            '<li>Enter your prompts.</li><li>Run the workflow.</li></ol></div>'})}}

    def guide(self, html):
        return ()
