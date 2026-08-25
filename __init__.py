from .h3_tag_references import H3TaggedReferencePrompt
from .built_in_references import H3BuiltInReference
from .server import register_routes


register_routes()

NODE_CLASS_MAPPINGS = {
    "H3TaggedReferencePrompt": H3TaggedReferencePrompt,
    "H3BuiltInReference": H3BuiltInReference,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3TaggedReferencePrompt": "H3 Tagged Reference Prompt",
    "H3BuiltInReference": "Built-In Reference",
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
