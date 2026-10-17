"""Load MIDI files from ComfyUI's input/output folders as YUE2_MIDI bytes."""

from pathlib import Path

import folder_paths
import mido
from comfy_api.latest import io


def midi_files():
    choices = []
    for label, root in (("input", folder_paths.get_input_directory()),
                        ("output", folder_paths.get_output_directory())):
        root = Path(root)
        if root.is_dir():
            choices.extend(f"{label}/{path.relative_to(root).as_posix()}"
                           for path in root.rglob("*")
                           if path.is_file() and path.suffix.lower() in (".mid", ".midi"))
    return sorted(choices, key=str.casefold) or ["No MIDI files found"]


def load_midi(selection):
    label, separator, relative = selection.partition("/")
    roots = {"input": Path(folder_paths.get_input_directory()).resolve(),
             "output": Path(folder_paths.get_output_directory()).resolve()}
    if not separator or label not in roots or not relative:
        raise ValueError("Select a .mid or .midi file from ComfyUI's input or output folder.")
    root = roots[label]
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in (".mid", ".midi"):
        raise ValueError("MIDI selection must stay inside the chosen ComfyUI folder.")
    if not path.is_file():
        raise FileNotFoundError(f"MIDI file was not found: {selection}. Refresh the node's file list.")
    data = path.read_bytes()
    try:
        from io import BytesIO
        mido.MidiFile(file=BytesIO(data))
    except Exception as error:
        raise ValueError(f"Selected file is not a readable MIDI: {selection}: {error}") from error
    return data


class SkebaLoadMIDI(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaLoadMIDI",
            display_name="Skeba Load MIDI",
            category="Skeba Music",
            description="Load a .mid/.midi file from ComfyUI input or output as YUE2_MIDI bytes.",
            inputs=[io.Combo.Input("file", options=midi_files())],
            outputs=[io.Custom("YUE2_MIDI").Output(display_name="midi")],
        )

    @classmethod
    def execute(cls, file):
        return io.NodeOutput(load_midi(file))
