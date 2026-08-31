"""Vendored GPLv3 SKEBA H3 Motion Context node package."""

import logging

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS


logging.getLogger("skeba_h3_motion_context").info(
    "skeba_h3_motion_context: SKEBA nodes registered from Skeba AI Nodes. "
    "ComfyUI patches install on the first run of a Motion Context node."
)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
