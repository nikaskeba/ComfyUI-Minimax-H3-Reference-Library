"""Set one canonical quarter-note tempo for both score and audio transcription."""

import math
import re

from comfy_api.latest import io


TEMPO_LINE = re.compile(r"(?m)^Q\s*:[^\r\n]*")


def set_abc_tempo(abc, bpm=0.0):
    if not isinstance(abc, str) or not abc.strip():
        raise ValueError("Connect a non-empty SheetSage ABC score.")
    bpm = float(bpm)
    if not math.isfinite(bpm) or bpm < 0 or (bpm != 0 and not 20 <= bpm <= 400):
        raise ValueError("bpm must be 0 (keep the ABC tempo) or between 20 and 400.")
    matches = list(TEMPO_LINE.finditer(abc))
    if len(matches) != 1:
        raise ValueError("ABC needs exactly one Q: tempo line before sharing it with both MIDI paths.")
    if bpm == 0:
        return abc
    value = f"{bpm:g}"
    match = matches[0]
    return abc[:match.start()] + f"Q:1/4={value}" + abc[match.end():]


class SkebaABCSharedTempo(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaABCSharedTempo",
            display_name="Skeba ABC Shared Tempo",
            category="Skeba Music",
            description="Apply one BPM to SheetSage ABC before feeding both ABC-to-MIDI and MuScriptor. 0 keeps SheetSage's BPM.",
            inputs=[io.String.Input("abc", multiline=True, force_input=True),
                    io.Float.Input("bpm", default=0.0, min=0.0, max=400.0, step=0.1)],
            outputs=[io.String.Output(display_name="abc")],
        )

    @classmethod
    def execute(cls, abc, bpm=0.0):
        return io.NodeOutput(set_abc_tempo(abc, bpm))
