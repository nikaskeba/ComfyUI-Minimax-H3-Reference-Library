from .h3_tag_references import H3TaggedReferencePrompt
from .built_in_references import H3BuiltInReference
from .batch_image_nodes import BatchImageLoaderNode, ImageFromBatchNode
from .motion_context import (
    NODE_CLASS_MAPPINGS as MOTION_CONTEXT_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as MOTION_CONTEXT_NODE_DISPLAY_NAME_MAPPINGS,
)
from .prompt_loop_node import PromptFromListNode, PromptLoopNode
from .skeba_io_tags import SkebaBypass
from .universal_bypass import SkebaUniversalBypass
from .video_loop_node import CombineVideoClipsNode
from .server import register_routes


register_routes()

NODE_CLASS_MAPPINGS = {
    "H3TaggedReferencePrompt": H3TaggedReferencePrompt,
    "H3BuiltInReference": H3BuiltInReference,
    "SkebaBatchImageLoaderNode": BatchImageLoaderNode,
    "SkebaImageFromBatchNode": ImageFromBatchNode,
    "SkebaPromptLoopNode": PromptLoopNode,
    "SkebaPromptFromListNode": PromptFromListNode,
    "SkebaCombineVideoClipsNode": CombineVideoClipsNode,
    "SkebaBypass": SkebaBypass,
    "SkebaUniversalBypass": SkebaUniversalBypass,
    **MOTION_CONTEXT_NODE_CLASS_MAPPINGS,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3TaggedReferencePrompt": "H3 Tagged Reference Prompt",
    "H3BuiltInReference": "Built-In Reference",
    "SkebaBatchImageLoaderNode": "Skeba Batch Images (Folder Loader)",
    "SkebaImageFromBatchNode": "Skeba Get Image From Batch",
    "SkebaPromptLoopNode": "Skeba Batch Text (Prompt Loop)",
    "SkebaPromptFromListNode": "Skeba Select Prompt From Batch",
    "SkebaCombineVideoClipsNode": "Skeba Combine Video Clips",
    "SkebaBypass": "Skeba Bypass",
    "SkebaUniversalBypass": "Universal Node Bypass",
    **MOTION_CONTEXT_NODE_DISPLAY_NAME_MAPPINGS,
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
