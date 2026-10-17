import os

import folder_paths
from symusic import Score
from comfy_api.latest import ComfyExtension, io

from .transcription import transcribe
from .yue2_dataset import SkebaYuE2TrainingDataset
from .muscriptor_grid import SkebaMuScriptorGrid
from .midi_merge import SkebaCombineTranscriptionMIDIs
from .abc_track_names import label_abc_tracks
from .midi_pattern_stabilizer import SkebaMIDIPatternStabilizer
from .midi_to_abc import SkebaMIDIToABC
from .midi_loader import SkebaLoadMIDI
from .abc_tempo import SkebaABCSharedTempo

class SkebaSheetSage2AudioToABC(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaSheetSage2AudioToABC",
            display_name="Skeba SheetSage2 Audio to ABC + MIDI",
            category="Skeba Music",
            description="Transcribes audio once into ABC and vocal/instrumental melody MIDI. Uses the native Load Audio Encoder node.",
            inputs=[
                io.AudioEncoder.Input("audio_encoder"),
                io.Audio.Input("audio"),
                io.Combo.Input("mode", options=["melody", "full"], tooltip="Controls ABC chord symbols. MIDI contains the vocal and instrumental melodies in both modes."),
                io.Combo.Input("abc_error_mode", options=["skip_invalid_notes", "strict"], default="skip_invalid_notes", optional=True,
                               tooltip="Skip notes too short for the decoded ABC rhythm grid, or report the original error. Raw MIDI is unchanged."),
            ],
            outputs=[
                io.String.Output(display_name="abc", is_output_list=True),
                io.Custom("YUE2_MIDI").Output(display_name="midi", is_output_list=True),
                io.String.Output(display_name="beat_map", is_output_list=True),
            ],
        )

    @classmethod
    def execute(cls, audio_encoder, audio, mode, abc_error_mode="skip_invalid_notes"):
        scores, midis, beat_maps = transcribe(audio_encoder, audio["waveform"], audio["sample_rate"], mode == "melody", abc_error_mode)
        return io.NodeOutput(scores, midis, beat_maps)


class SkebaABCToMidi(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaABCToMidi",
            display_name="Skeba ABC to MIDI",
            category="Skeba Music",
            description="Converts ABC notation to MIDI using the score's tempo, rhythm, key signature, and separate voices. Connect to Skeba Save MIDI to save a file.",
            inputs=[io.String.Input("abc", multiline=True)],
            outputs=[io.Custom("YUE2_MIDI").Output(display_name="midi")],
        )

    @classmethod
    def execute(cls, abc):
        if not abc.strip():
            raise ValueError("ABC is empty. Paste a score or connect an ABC output.")
        score = Score.from_abc(abc)
        label_abc_tracks(abc, score)
        return io.NodeOutput(score.dumps_midi())


class SkebaSaveMidi(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaSaveMidi",
            display_name="Skeba Save MIDI",
            category="Skeba Music",
            is_output_node=True,
            inputs=[
                io.Custom("YUE2_MIDI").Input("midi"),
                io.String.Input("filename_prefix", default="Skeba Music/melody"),
            ],
            outputs=[io.String.Output(display_name="path")],
        )

    @classmethod
    def execute(cls, midi, filename_prefix):
        folder, filename, counter, _, _ = folder_paths.get_save_image_path(filename_prefix, folder_paths.get_output_directory())
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{filename}_{counter:05}_.mid")
        with open(path, "wb") as stream:
            stream.write(midi)
        return io.NodeOutput(path)


class SkebaMusic(ComfyExtension):
    async def get_node_list(self):
        return MUSIC_NODE_CLASSES


MUSIC_NODE_CLASSES = [
    SkebaSheetSage2AudioToABC, SkebaABCToMidi, SkebaSaveMidi,
    SkebaYuE2TrainingDataset, SkebaMuScriptorGrid,
    SkebaCombineTranscriptionMIDIs, SkebaMIDIPatternStabilizer,
    SkebaMIDIToABC, SkebaLoadMIDI, SkebaABCSharedTempo,
]


async def comfy_entrypoint():
    return SkebaMusic()
