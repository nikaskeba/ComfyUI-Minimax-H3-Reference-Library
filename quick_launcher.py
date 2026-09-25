class SkebaQuickLauncher:
    CATEGORY = "Skeba AI Nodes - Reference"
    RETURN_TYPES = ()
    FUNCTION = "launch"
    OUTPUT_NODE = False

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    def launch(self):
        return ()
