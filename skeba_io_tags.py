"""Skeba workflow tagging passthrough node."""


class _AnyType(str):
    """ComfyUI wildcard type helper used by passthrough-style nodes."""

    def __ne__(self, other):
        return False


ANY_TYPE = _AnyType("*")


class SkebaBypass:
    """Route an optional value and expose a named enabled-state signal."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "input_2"}),
                "bypass": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "input": (ANY_TYPE,),
            },
        }

    RETURN_TYPES = (ANY_TYPE, "STRING", "BOOLEAN")
    RETURN_NAMES = ("output", "name", "enabled")
    FUNCTION = "route"
    CATEGORY = "Skeba AI Nodes - Utilities"

    def route(self, name, bypass, input=None):
        enabled = (not bypass) and (input is not None)
        return (input if enabled else None, name, enabled)
