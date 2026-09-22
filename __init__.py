from .refmod_preview import SkebaRefModPreview
from .refmod_studio import SkebaRefModStudio
from .refmod_create import SkebaCreateH3RefMod
from .refmod_apply import SkebaH3RefModApply
from .palette_sampling import PaletteFramePreview
from .fixed_palette import FixedPaletteQuantize
from .h3_tag_references import H3TaggedReferencePrompt, H3PromptListValidator
from .built_in_references import H3BuiltInReference
from .cached_h3_reference import (
    SkebaCachedMiniMaxH3ReferenceFirstLast,
    SkebaCachedMiniMaxH3ReferenceToVideo,
)
from .h3_guide_resize import SkebaH3GuideResizeToLatent
from .h3_guide_bypass import SkebaMiniMaxH3AddGuideBypass
from .h3_multi_guide import SkebaMiniMaxH3MultiFrameGuideTest
from .h3_av_connector import (
    SkebaH3AVConnectorAssembleTest,
    SkebaH3AVConnectorFinalizeTest,
    SkebaMiniMaxH3AVConnectorGuideTest,
)
from .h3_last_frame_store import SkebaH3LoopGuideImage, SkebaH3SaveLastFrame
from .h3_last_frame_exposure import SkebaH3LastFrameExposureMatch
from .batch_image_nodes import BatchImageLoaderNode, ImageFromBatchNode
from .motion_context import (
    NODE_CLASS_MAPPINGS as MOTION_CONTEXT_NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS as MOTION_CONTEXT_NODE_DISPLAY_NAME_MAPPINGS,
)
from .prompt_loop_node import PromptFromListNode, PromptLoopNode
from .skeba_io_tags import SkebaBypass
from .universal_bypass import SkebaUniversalBypass
from .video_loop_node import CombineVideoClipsNode
from .disk_video import SaveClipToFile, CompilePlaylist, FinishPlaylist
from .playlist_editor import PlaylistRedoInput, PlaylistRedoSave
from .server import register_routes


register_routes()

NODE_CLASS_MAPPINGS = {
    "SkebaRefModPreview": SkebaRefModPreview,
    "SkebaRefModStudio": SkebaRefModStudio,
    "SkebaCreateH3RefMod": SkebaCreateH3RefMod,
    "SkebaH3RefModApply": SkebaH3RefModApply,
    "SkebaSaveClipToFile": SaveClipToFile,
    "SkebaCompilePlaylist": CompilePlaylist,
    "SkebaFinishPlaylist": FinishPlaylist,
    "SkebaPlaylistRedoInput": PlaylistRedoInput,
    "SkebaPlaylistRedoSave": PlaylistRedoSave,
    "SkebaPaletteFramePreview": PaletteFramePreview,
    "SkebaFixedPaletteQuantize": FixedPaletteQuantize,
    "H3TaggedReferencePrompt": H3TaggedReferencePrompt,
    "SKEBAH3PromptListValidator": H3PromptListValidator,
    "H3BuiltInReference": H3BuiltInReference,
    "SkebaCachedMiniMaxH3ReferenceToVideo": SkebaCachedMiniMaxH3ReferenceToVideo,
    "SkebaCachedMiniMaxH3ReferenceFirstLast": SkebaCachedMiniMaxH3ReferenceFirstLast,
    "SkebaH3GuideResizeToLatent": SkebaH3GuideResizeToLatent,
    "SkebaMiniMaxH3AddGuideBypass": SkebaMiniMaxH3AddGuideBypass,
    "SkebaMiniMaxH3MultiFrameGuideTest": SkebaMiniMaxH3MultiFrameGuideTest,
    "SkebaMiniMaxH3AVConnectorGuideTest": SkebaMiniMaxH3AVConnectorGuideTest,
    "SkebaH3AVConnectorFinalizeTest": SkebaH3AVConnectorFinalizeTest,
    "SkebaH3AVConnectorAssembleTest": SkebaH3AVConnectorAssembleTest,
    "SkebaH3LoopGuideImage": SkebaH3LoopGuideImage,
    "SkebaH3SaveLastFrame": SkebaH3SaveLastFrame,
    "SkebaH3LastFrameExposureMatch": SkebaH3LastFrameExposureMatch,
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
    "SkebaRefModPreview": "SKEBA RefMod Frame / Audio Preview",
    "SkebaRefModStudio": "SKEBA RefMod Studio Create / Edit",
    "SkebaCreateH3RefMod": "SKEBA Create H3 RefMod",
    "SkebaH3RefModApply": "SKEBA Apply H3 RefMod",
    "SkebaSaveClipToFile": "Skeba Save Clip to File",
    "SkebaCompilePlaylist": "Skeba Create Playlist Video",
    "SkebaFinishPlaylist": "Skeba Finish Live Playlist",
    "SkebaPlaylistRedoInput": "Skeba Playlist Redo Input",
    "SkebaPlaylistRedoSave": "Skeba Playlist Redo Save",
    "SkebaPaletteFramePreview": "Palette Frame Preview",
    "SkebaFixedPaletteQuantize": "Fixed Palette Quantize",
    "H3TaggedReferencePrompt": "H3 Tagged Reference Prompt",
    "SKEBAH3PromptListValidator": "SKEBA H3 Prompt List Validator",
    "H3BuiltInReference": "Built-In Reference",
    "SkebaCachedMiniMaxH3ReferenceToVideo": "SKEBA MiniMax H3 Cached Reference to Video",
    "SkebaCachedMiniMaxH3ReferenceFirstLast": "SKEBA MiniMax H3 Cached Reference + First/Last Frame",
    "SkebaH3GuideResizeToLatent": "H3 Guide Resize to Latent",
    "SkebaMiniMaxH3AddGuideBypass": "SKEBA MiniMax H3 Add Guide with Bypass",
    "SkebaMiniMaxH3MultiFrameGuideTest": "SKEBA MiniMax H3 Multi-Frame Guide",
    "SkebaMiniMaxH3AVConnectorGuideTest": "SKEBA MiniMax H3 AV Connector Guide",
    "SkebaH3AVConnectorFinalizeTest": "SKEBA H3 AV Connector Finalize",
    "SkebaH3AVConnectorAssembleTest": "SKEBA H3 AV Connector Assemble",
    "SkebaH3LoopGuideImage": "H3 Loop Guide Image",
    "SkebaH3SaveLastFrame": "H3 Save Last Frame",
    "SkebaH3LastFrameExposureMatch": "H3 Last Frame Exposure Match",
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
