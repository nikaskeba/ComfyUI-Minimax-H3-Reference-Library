"""User-defined choices for shared workflow controls."""
import math
import re

from .skeba_io_tags import ANY_TYPE


class SkebaCustomChoice:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "choices": ("STRING", {"default": "5\n22\n39\n56", "multiline": True}),
            "selected": ("STRING", {"default": "22"}),
            "output_type": (["text", "integer", "decimal", "boolean"], {"default": "text"}),
        }}

    RETURN_TYPES = (ANY_TYPE,)
    RETURN_NAMES = ("value",)
    FUNCTION = "choose"
    CATEGORY = "Skeba AI Nodes - Utilities"
    DESCRIPTION = "Choose a custom value and share it through Setter/Getter. Use text for combo inputs, including numeric-looking choices."

    def choose(self, choices, selected, output_type="text"):
        options = list(dict.fromkeys(value.strip() for value in re.split(r"[\r\n,]+", choices) if value.strip()))
        if not options:
            raise ValueError("Custom Choice: add at least one choice.")
        if selected not in options:
            raise ValueError("Custom Choice: select a value from the current choices.")
        if output_type == "text":
            return (selected,)
        try:
            if output_type == "integer":
                return (int(selected),)
            if output_type == "decimal":
                value = float(selected)
                if math.isfinite(value):
                    return (value,)
            if output_type == "boolean" and selected.lower() in ("true", "false"):
                return (selected.lower() == "true",)
        except ValueError:
            pass
        raise ValueError(f"Custom Choice: {selected!r} is not a valid {output_type} value.")
