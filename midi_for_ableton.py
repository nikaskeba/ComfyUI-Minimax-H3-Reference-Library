"""Retempo a MuScriptor MIDI file while keeping note times aligned to audio."""

import math
from pathlib import Path

import folder_paths


class SkebaMidiForAbleton:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "midi_path": ("STRING", {"default": ""}),
            "bpm": ("FLOAT", {"default": 120.0, "min": 1.0, "max": 400.0, "step": 0.01}),
            "tempo_rounding": (["2 decimals", "whole BPM", "exact"], {"default": "2 decimals"}),
        }}

    RETURN_TYPES = ("STRING", "FLOAT")
    RETURN_NAMES = ("ableton_midi_path", "bpm_used")
    FUNCTION = "prepare"
    CATEGORY = "SKEBA/Music"
    DESCRIPTION = "Set an Ableton-ready MIDI tempo while preserving MuScriptor note timing against the source audio."

    def prepare(self, midi_path, bpm, tempo_rounding):
        try:
            import mido
        except ImportError as exc:
            raise RuntimeError("Install MuScriptor's requirements to enable MIDI export (mido is missing).") from exc

        output_root = Path(folder_paths.get_output_directory()).resolve()
        source = Path(midi_path).resolve()
        if not source.is_relative_to(output_root) or source.suffix.lower() != ".mid" or not source.is_file():
            raise ValueError("Select an existing .mid file inside ComfyUI/output.")
        if not math.isfinite(bpm) or bpm <= 0:
            raise ValueError("BPM must be a positive finite number.")
        if tempo_rounding == "2 decimals":
            bpm = round(bpm, 2)
        elif tempo_rounding == "whole BPM":
            bpm = round(bpm)
        elif tempo_rounding != "exact":
            raise ValueError(f"Unknown tempo rounding: {tempo_rounding}")

        midi = mido.MidiFile(source)
        if midi.type != 1:
            raise ValueError("Expected MuScriptor's multi-track MIDI (type 1).")
        tempo_events = []
        for track in midi.tracks:
            tick = 0
            for message in track:
                tick += message.time
                if message.type == "set_tempo":
                    tempo_events.append((tick, message.tempo))
        if len(tempo_events) != 1 or tempo_events[0][0] != 0:
            raise ValueError("Expected one constant tempo at the start of the MuScriptor MIDI.")

        old_tempo = tempo_events[0][1]
        new_tempo = round(60_000_000 / bpm)
        if new_tempo < 1:
            raise ValueError("BPM is too high for MIDI tempo encoding.")
        for track in midi.tracks:
            old_tick = 0
            new_tick = 0
            rewritten = mido.MidiTrack()
            for message in track:
                old_tick += message.time
                if message.type == "set_tempo":
                    continue
                target_tick = round(old_tick * old_tempo / new_tempo)
                rewritten.append(message.copy(time=target_tick - new_tick))
                new_tick = target_tick
            track[:] = rewritten
        midi.tracks[0].insert(0, mido.MetaMessage("set_tempo", tempo=new_tempo, time=0))

        bpm_used = 60_000_000 / new_tempo
        if tempo_rounding == "2 decimals":
            bpm_used = round(bpm_used, 2)
        elif tempo_rounding == "whole BPM":
            bpm_used = round(bpm_used)
        else:
            bpm_used = round(bpm_used, 6)
        base = f"{source.stem}_ableton_{bpm_used:.2f}bpm"
        destination = source.with_name(f"{base}.mid")
        index = 2
        while destination.exists():
            destination = source.with_name(f"{base}_{index}.mid")
            index += 1
        midi.save(destination)
        return str(destination), bpm_used
