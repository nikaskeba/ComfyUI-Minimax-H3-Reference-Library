from .voice_description_refmod import SkebaRefModVoiceDescription
from .refmod_preview import SkebaRefModPreview
from .reference_audio_preview import SkebaH3ReferenceAudioPreview
from .quick_launcher import SkebaQuickLauncher
from .custom_choice import SkebaCustomChoice
from .midi_for_ableton import SkebaMidiForAbleton
from .compiler_templates import SkebaH3CompilerTemplates
from .last_rendered_context import SkebaH3LastRenderedContext
from .workflow_guide import SkebaWorkflowGuide
from .h3_audio_refine import SkebaH3AudioRefine, SkebaH3AudioInpaintRange, SkebaH3AudioEditMask, SkebaH3VideoEditMask, SkebaH3VideoLatentAnchorBlend, SkebaH3FinishInpaintLatent, SkebaH3AVInpaintRange
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
from .h3_upscale_context import SkebaH3UpscaleContextGuides
from .h3_person_reference_mask import SkebaPersonReferenceMask
from .h3_mask_composite import SkebaH3FinalInpaintComposite
from .h3_inpaint_source_loop import SkebaH3InpaintBatchFit, SkebaH3InpaintWindowPlan, SkebaH3InpaintSourceWindow, SkebaH3InpaintWindowValidate
from .h3_inpaint_mode import SkebaH3InpaintLatentMode, SkebaH3InpaintVideoMode
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
from .prompt_loop_node import PromptFromListNode, PromptLoopNode, PromptListTextNode
from .skeba_io_tags import SkebaBypass
from .universal_bypass import SkebaUniversalBypass
from .video_loop_node import CombineVideoClipsNode
from .disk_video import SaveClipToFile, CompilePlaylist, FinishPlaylist
from .playlist_registration import PlaylistWorkflow
from .playlist_editor import PlaylistRedoInput, PlaylistRedoSave
from .server import register_routes
from .skeba_music import MUSIC_NODE_CLASSES
from .skeba_video_prompt import NODE_CLASSES as VIDEO_PROMPT_NODE_CLASSES


register_routes()

MUSIC_NODE_CLASS_MAPPINGS = {
    node.GET_SCHEMA().node_id: node for node in MUSIC_NODE_CLASSES
}
VIDEO_PROMPT_NODE_CLASS_MAPPINGS = {
    node.GET_SCHEMA().node_id: node for node in VIDEO_PROMPT_NODE_CLASSES
}

NODE_CLASS_MAPPINGS = {
    "SkebaRefModVoiceDescription": SkebaRefModVoiceDescription,
    "SkebaH3ReferenceAudioPreview": SkebaH3ReferenceAudioPreview,
    "SkebaH3LastRenderedContext": SkebaH3LastRenderedContext,
    "SkebaCustomChoice": SkebaCustomChoice,
    "SkebaMidiForAbleton": SkebaMidiForAbleton,
    "SkebaH3CompilerTemplates": SkebaH3CompilerTemplates,
    "SkebaWorkflowGuide": SkebaWorkflowGuide,
    "SkebaPromptListText": PromptListTextNode,
    "SkebaQuickLauncher": SkebaQuickLauncher,
    "SkebaH3AudioRefine": SkebaH3AudioRefine,
    "SkebaH3AudioInpaintRange": SkebaH3AudioInpaintRange,
    "SkebaH3AudioEditMask": SkebaH3AudioEditMask,
    "SkebaH3VideoEditMask": SkebaH3VideoEditMask,
    "SkebaH3VideoLatentAnchorBlend": SkebaH3VideoLatentAnchorBlend,
    "SkebaH3FinishInpaintLatent": SkebaH3FinishInpaintLatent,
    "SkebaH3AVInpaintRange": SkebaH3AVInpaintRange,
    "SkebaRefModPreview": SkebaRefModPreview,
    "SkebaRefModStudio": SkebaRefModStudio,
    "SkebaCreateH3RefMod": SkebaCreateH3RefMod,
    "SkebaH3RefModApply": SkebaH3RefModApply,
    "SkebaSaveClipToFile": SaveClipToFile,
    "SkebaCompilePlaylist": CompilePlaylist,
    "SkebaFinishPlaylist": FinishPlaylist,
    "SkebaPlaylistWorkflow": PlaylistWorkflow,
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
    "SkebaH3UpscaleContextGuides": SkebaH3UpscaleContextGuides,
    "SkebaPersonReferenceMask": SkebaPersonReferenceMask,
    "SkebaH3FinalInpaintComposite": SkebaH3FinalInpaintComposite,
    "SkebaH3InpaintBatchFit": SkebaH3InpaintBatchFit,
    "SkebaH3InpaintWindowPlan": SkebaH3InpaintWindowPlan,
    "SkebaH3InpaintSourceWindow": SkebaH3InpaintSourceWindow,
    "SkebaH3InpaintWindowValidate": SkebaH3InpaintWindowValidate,
    "SkebaH3InpaintLatentMode": SkebaH3InpaintLatentMode,
    "SkebaH3InpaintVideoMode": SkebaH3InpaintVideoMode,
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
    **MUSIC_NODE_CLASS_MAPPINGS,
    **VIDEO_PROMPT_NODE_CLASS_MAPPINGS,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SkebaRefModVoiceDescription": "SKEBA RefMod Voice Description",
    "SkebaH3ReferenceAudioPreview": "SKEBA H3 Reference Audio Preview",
    "SkebaH3LastRenderedContext": "SKEBA H3 Last Rendered Context",
    "SkebaCustomChoice": "SKEBA Custom Choice",
    "SkebaMidiForAbleton": "SKEBA MIDI for Ableton",
    "SkebaH3CompilerTemplates": "SKEBA H3 Compiler Templates",
    "SkebaWorkflowGuide": "SKEBA Workflow Guide (HTML)",
    "SkebaPromptListText": "SKEBA Prompt List Text",
    "SkebaQuickLauncher": "SKEBA Quick Launcher",
    "SkebaH3AudioRefine": "SKEBA H3 Audio Refine (Optional)",
    "SkebaH3AudioInpaintRange": "SKEBA H3 Audio Inpaint Range (Experimental)",
    "SkebaH3AudioEditMask": "SKEBA H3 Audio Edit Mask (Before Sampling)",
    "SkebaH3VideoEditMask": "SKEBA H3 Video Edit Mask (Before Sampling)",
    "SkebaH3VideoLatentAnchorBlend": "SKEBA H3 Video Latent Anchor Blend",
    "SkebaH3FinishInpaintLatent": "SKEBA H3 Finish Inpaint Latent",
    "SkebaH3AVInpaintRange": "SKEBA H3 Video + Audio Inpaint Range (Experimental)",
    "SkebaRefModPreview": "SKEBA RefMod Frame / Audio Preview",
    "SkebaRefModStudio": "SKEBA RefMod Studio Create / Edit",
    "SkebaCreateH3RefMod": "SKEBA Create H3 RefMod",
    "SkebaH3RefModApply": "SKEBA Apply H3 RefMod",
    "SkebaSaveClipToFile": "Skeba Save Clip to File",
    "SkebaCompilePlaylist": "Skeba Create Playlist Video",
    "SkebaFinishPlaylist": "Skeba Finish Live Playlist",
    "SkebaPlaylistWorkflow": "SKEBA Playlist Workflow — Register / Update",
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
    "SkebaH3UpscaleContextGuides": "SKEBA H3 Upscale Context Guides",
    "SkebaPersonReferenceMask": "SKEBA Reference Subject Mask (2 Tracks)",
    "SkebaH3FinalInpaintComposite": "SKEBA H3 Final Inpaint Composite",
    "SkebaH3InpaintBatchFit": "SKEBA H3 Inpaint Batch Fit",
    "SkebaH3InpaintWindowPlan": "SKEBA H3 Inpaint Loop Window Plan",
    "SkebaH3InpaintSourceWindow": "SKEBA H3 Inpaint Source Window",
    "SkebaH3InpaintWindowValidate": "SKEBA H3 Inpaint Loop Validate",
    "SkebaH3InpaintLatentMode": "SKEBA H3 Inpaint / Audio-Driven Latent",
    "SkebaH3InpaintVideoMode": "SKEBA H3 Inpaint / Audio-Driven Video",
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
    **{node_id: node.GET_SCHEMA().display_name
       for node_id, node in MUSIC_NODE_CLASS_MAPPINGS.items()},
    **{node_id: node.GET_SCHEMA().display_name
       for node_id, node in VIDEO_PROMPT_NODE_CLASS_MAPPINGS.items()},
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
