"""Local, offline VLM video-to-prompt nodes adapted from ComfyUI-VideoAnalyzer."""

from .nodes import SkebaH3LocalVLMLoader, SkebaH3VideoToPrompt

NODE_CLASSES = (SkebaH3LocalVLMLoader, SkebaH3VideoToPrompt)
