"""MuScriptor transcription placed on a SheetSage ABC rhythm grid."""

import io as byte_io
from bisect import bisect_right
import json
import math
import os
import re
from pathlib import Path

import folder_paths
import mido
from comfy_api.latest import io
from huggingface_hub.errors import LocalEntryNotFoundError
from symusic import Score


TICKS_PER_BEAT = 480
GRID_TICKS = TICKS_PER_BEAT // 4
INSTRUMENT_OPTIONS = (
    "drums", "acoustic_piano", "electric_piano", "chromatic_percussion", "organ",
    "acoustic_guitar", "clean_electric_guitar", "distorted_electric_guitar",
    "acoustic_bass", "electric_bass", "violin", "viola", "cello", "contrabass",
    "orchestral_harp", "timpani", "string_ensemble", "synth_strings", "voice",
    "orchestra_hit", "trumpet", "trombone", "tuba", "french_horn",
    "brass_section", "soprano_and_alto_sax", "tenor_sax", "baritone_sax",
    "oboe", "english_horn", "bassoon", "clarinet", "flutes", "synth_lead",
    "synth_pad",
)
NO_INSTRUMENTS = "__none__"


def local_model_source(model_size):
    """Use a complete cached MuScriptor checkpoint without a Hub request."""
    from huggingface_hub import try_to_load_from_cache

    repo = f"MuScriptor/muscriptor-{model_size}"
    cache_roots = [None, Path.home() / ".cache" / "huggingface" / "hub"]
    for cache_root in cache_roots:
        candidate = try_to_load_from_cache(repo, "model.safetensors", cache_dir=cache_root)
        if isinstance(candidate, str):
            path = Path(candidate)
            if path.is_file() and (path.parent / "config.json").is_file():
                return path
    return model_size


def parse_abc_grid(abc):
    if not isinstance(abc, str) or not abc.strip():
        raise ValueError("Connect a non-empty SheetSage ABC score to abc.")
    if not re.search(r"(?m)^\s*Q\s*:", abc) or not re.search(r"(?m)^\s*M\s*:", abc):
        raise ValueError("ABC needs explicit Q: tempo and M: meter for the rhythm grid.")
    try:
        score = Score.from_abc(abc)
        tempos = list(score.tempos)
        meters = list(score.time_signatures)
        if not tempos or not meters:
            raise ValueError("ABC must decode to a tempo and meter for grid alignment.")
        # ABC files can repeat an unchanged Q: or M: later in the score. Those
        # produce extra events, but do not change the constant MIDI grid.
        if any(not math.isclose(float(event.qpm), float(tempos[0].qpm), rel_tol=1e-5)
               for event in tempos[1:]):
            raise ValueError(
                "ABC changes tempo within the song. This node exports one constant MIDI tempo; "
                "use a constant-tempo ABC score for grid alignment."
            )
        if any((int(event.numerator), int(event.denominator)) !=
               (int(meters[0].numerator), int(meters[0].denominator))
               for event in meters[1:]):
            raise ValueError(
                "ABC changes meter within the song. This node exports one constant MIDI meter; "
                "use a constant-meter ABC score for grid alignment."
            )
        qpm = float(tempos[0].qpm)
        numerator = int(meters[0].numerator)
        denominator = int(meters[0].denominator)
        if not math.isfinite(qpm) or qpm <= 0 or numerator <= 0 or denominator <= 0 or denominator & (denominator - 1):
            raise ValueError("ABC tempo or meter is invalid.")
        last_tick = max((note.time + note.duration for track in score.tracks for note in track.notes), default=0)
        abc_seconds = last_tick / score.ticks_per_quarter * 60 / qpm
        return qpm, numerator, denominator, abc_seconds
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(f"ABC rhythm could not be decoded: {error}") from error


def parse_beat_map(value):
    """Validate SheetSage's optional audio-time to score-position map."""
    if not value:
        return None
    try:
        data = json.loads(value)
        if data.get("version") != 1:
            raise ValueError("unsupported version")
        times = [float(number) for number in data["times"]]
        quarters = [float(number) for number in data["quarters"]]
        duration = float(data["source_duration"])
        if len(times) != len(quarters) or len(times) < 2:
            raise ValueError("times and quarters need matching points")
        if not all(math.isfinite(number) for number in (*times, *quarters, duration)) or duration <= 0:
            raise ValueError("non-finite or invalid values")
        if any(right <= left for left, right in zip(times, times[1:])):
            raise ValueError("beat times must increase")
        if any(right <= left for left, right in zip(quarters, quarters[1:])) or quarters[0] < 0:
            raise ValueError("score positions must increase from zero or later")
        return times, quarters, duration
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise ValueError(f"SheetSage beat_map is invalid: {error}") from error


def score_position_at(time, beat_map):
    """Interpolate the decoded beats, extending the end intervals if necessary."""
    times, quarters, _ = beat_map
    index = max(0, min(bisect_right(times, time) - 1, len(times) - 2))
    portion = (time - times[index]) / (times[index + 1] - times[index])
    return quarters[index] + portion * (quarters[index + 1] - quarters[index])


def quantize_events(events, qpm, program_for_instrument, invalid_notes, beat_map=None):
    from muscriptor.events import NoteStartEvent, NoteEndEvent

    if invalid_notes not in ("Skip malformed", "Strict error"):
        raise ValueError(f"Unknown invalid_notes mode: {invalid_notes}")
    starts = {}
    notes = []
    skipped = 0

    def invalid(reason):
        nonlocal skipped
        if invalid_notes == "Strict error":
            raise ValueError(f"Malformed MuScriptor note: {reason}")
        skipped += 1

    for event in events:
        if isinstance(event, NoteStartEvent):
            if event.index in starts:
                invalid(f"duplicate start index {event.index}")
            starts[event.index] = event
        elif isinstance(event, NoteEndEvent):
            start = starts.pop(event.start_event_index, None)
            if start is None:
                invalid(f"end without start index {event.start_event_index}")
                continue
            try:
                pitch = start.pitch
                onset = float(start.start_time)
                offset = float(event.end_time)
                if not isinstance(pitch, int) or not 0 <= pitch <= 127:
                    raise ValueError(f"pitch {pitch!r} is outside MIDI range")
                if not math.isfinite(onset) or not math.isfinite(offset) or onset < 0 or offset <= onset:
                    raise ValueError(f"invalid times {onset!r}–{offset!r}")
                program = 128 if start.instrument == "drums" else int(program_for_instrument(start.instrument))
                if not 0 <= program <= 128:
                    raise ValueError(f"instrument {start.instrument!r} is outside MIDI range")
            except (ValueError, TypeError, OverflowError, KeyError) as error:
                invalid(str(error))
                continue
            if beat_map is None:
                start_grid = round(onset * qpm / 60 * 4)
                end_grid = round(offset * qpm / 60 * 4)
            else:
                start_grid = round(score_position_at(onset, beat_map) * 4)
                end_grid = round(score_position_at(offset, beat_map) * 4)
            start_grid = max(0, start_grid)
            end_grid = max(start_grid + 1, end_grid)
            notes.append({"instrument": start.instrument, "program": program, "pitch": pitch,
                          "start_tick": start_grid * GRID_TICKS, "end_tick": end_grid * GRID_TICKS})

    for index in starts:
        invalid(f"start without end index {index}")

    notes.sort(key=lambda note: (note["program"], note["pitch"], note["start_tick"], note["end_tick"]))
    previous = {}
    resolved = []
    for note in notes:
        key = note["program"], note["pitch"]
        prior = previous.get(key)
        if prior is not None and prior["end_tick"] > note["start_tick"]:
            if prior["start_tick"] == note["start_tick"]:
                # Two onsets on the same grid point cannot retrigger independently.
                prior["end_tick"] = max(prior["end_tick"], note["end_tick"])
                continue
            prior["end_tick"] = note["start_tick"]
        resolved.append(note)
        previous[key] = note
    resolved.sort(key=lambda note: (note["start_tick"], note["program"], note["pitch"]))
    return resolved, skipped


def encode_midi(notes, qpm, numerator, denominator):
    midi = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
    tempo = round(60_000_000 / qpm)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=numerator, denominator=denominator, time=0))
    midi.tracks.append(meta)

    groups = {}
    for note in notes:
        groups.setdefault((note["program"], note["instrument"]), []).append(note)
    melodic_groups = sum(program != 128 for program, _ in groups)
    if melodic_groups > 15:
        raise ValueError("MIDI supports at most 15 simultaneous melodic instrument channels; narrow MuScriptor's instruments selection.")
    melodic_channels = iter(channel for channel in range(16) if channel != 9)
    for (program, instrument), group in groups.items():
        is_drum = program == 128
        if is_drum:
            track_channel = 9
        else:
            track_channel = next(melodic_channels)
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=instrument, time=0))
        if not is_drum:
            track.append(mido.Message("program_change", channel=track_channel, program=program, time=0))
        changes = []
        for note in group:
            changes.append((note["start_tick"], 1, note["pitch"]))
            changes.append((note["end_tick"], 0, note["pitch"]))
        prior_tick = 0
        for tick, on, pitch in sorted(changes):
            track.append(mido.Message("note_on" if on else "note_off", channel=track_channel,
                                      note=pitch, velocity=80 if on else 0, time=tick - prior_tick))
            prior_tick = tick
        midi.tracks.append(track)
    stream = byte_io.BytesIO()
    midi.save(file=stream)
    return stream.getvalue()


def notes_to_json(notes, qpm):
    tempo = round(60_000_000 / qpm)
    seconds_per_tick = tempo / 1_000_000 / TICKS_PER_BEAT
    return json.dumps([{"instrument": note["instrument"], "program": note["program"],
                        "pitch": note["pitch"], "start_time": round(note["start_tick"] * seconds_per_tick, 6),
                        "end_time": round(note["end_tick"] * seconds_per_tick, 6),
                        "start_tick": note["start_tick"], "end_tick": note["end_tick"]}
                       for note in notes], indent=2)


class SkebaMuScriptorGrid(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaMuScriptorGrid",
            display_name="SKEBA MuScriptor Transcribe Audio to MIDI",
            category="Skeba Music",
            description="Transcribe with MuScriptor; snap notes to the connected SheetSage ABC tempo and 16th-note grid.",
            inputs=[
                io.String.Input("abc", multiline=True, force_input=True, tooltip="Connect the ABC made from the same full-length song."),
                io.Combo.Input("model_size", options=["small", "medium", "large"], default="medium"),
                io.Combo.Input("device", options=["auto", "cpu", "cuda", "mps"], default="auto"),
                io.Combo.Input("dtype", options=["auto", "float32", "float16", "bfloat16"], default="auto"),
                io.Boolean.Input("use_sampling", default=False),
                io.Float.Input("temperature", default=1.0, min=0.0, max=2.0, step=0.05),
                io.Float.Input("cfg_coef", default=1.0, min=0.0, max=10.0, step=0.1),
                io.Int.Input("beam_size", default=1, min=1, max=10, step=1),
                io.Boolean.Input("prelude_forcing", default=True),
                io.Boolean.Input("strict_eos", default=False),
                io.String.Input("filename_prefix", default="Skeba Music/muscriptor_grid"),
                io.Combo.Input("invalid_notes", options=["Skip malformed", "Strict error"], default="Skip malformed"),
                io.Audio.Input("audio", optional=True),
                io.String.Input("audio_path", default="", optional=True),
                io.String.Input("instruments", default="", optional=True,
                                extra_dict={"instrumentOptions": list(INSTRUMENT_OPTIONS)}),
                io.Float.Input("tempo_override_bpm", default=0.0, min=0.0, max=400.0, step=1.0,
                               optional=True,
                               tooltip="0 uses the ABC tempo. Set the song's actual BPM if the ABC tempo causes notes to drift across bars."),
                io.String.Input("beat_map", optional=True, force_input=True,
                                tooltip="Connect SheetSage's beat_map output from the same audio. Its decoded beats place MuScriptor notes on SheetSage's actual score grid."),
            ],
            outputs=[io.String.Output(display_name="midi_path"),
                     io.String.Output(display_name="notes_json"),
                     io.Custom("YUE2_MIDI").Output(display_name="midi")],
        )

    @classmethod
    def execute(cls, abc, model_size, device, dtype, use_sampling, temperature, cfg_coef,
                beam_size, prelude_forcing, strict_eos, filename_prefix,
                invalid_notes="Skip malformed", audio=None, audio_path="", instruments="",
                tempo_override_bpm=0.0, beat_map=""):
        abc_qpm, numerator, denominator, abc_seconds = parse_abc_grid(abc)
        decoded_beat_map = parse_beat_map(beat_map)
        override = float(tempo_override_bpm)
        if not math.isfinite(override) or override < 0 or (override != 0 and not 20 <= override <= 400):
            raise ValueError("tempo_override_bpm must be 0 (ABC tempo) or between 20 and 400 BPM.")
        qpm = override or abc_qpm
        if override and abs(qpm - abc_qpm) > 0.01:
            print(f"[SKEBA MuScriptor] Using {qpm:g} BPM instead of ABC's {abc_qpm:g} BPM for note quantization and MIDI export.")
        try:
            from muscriptor.comfy_node import get_model, resolve_instrument_names
            from muscriptor.events import ProgressEvent
        except ImportError as error:
            raise RuntimeError("Install and enable ComfyUI-MuScriptor to use this node.") from error

        if audio is not None:
            waveform = audio["waveform"]
            sample_rate = int(audio["sample_rate"])
            if sample_rate <= 0 or waveform.shape[-1] == 0:
                raise ValueError("Audio is empty or has an invalid sample rate.")
            source_seconds = waveform.shape[-1] / sample_rate
            source = (waveform[0] if waveform.ndim == 3 else waveform, sample_rate)
        elif audio_path.strip():
            from muscriptor.utils.audio import load_audio
            source = audio_path.strip()
            if not os.path.isfile(source):
                raise FileNotFoundError(f"Audio file does not exist: {source}")
            source_seconds = load_audio(source).shape[-1] / 16000
        else:
            raise ValueError("Connect audio or provide audio_path.")

        if abs(abc_seconds - source_seconds) > max(2.0, source_seconds * 0.05):
            print(f"[SKEBA MuScriptor] ABC is {abc_seconds:.2f}s; audio is {source_seconds:.2f}s. Notes are not stretched.")
        if decoded_beat_map and abs(decoded_beat_map[2] - source_seconds) > max(0.5, source_seconds * 0.01):
            raise ValueError("SheetSage beat_map and MuScriptor audio have different durations. Connect the same full-length song to both nodes.")

        if instruments.strip() == NO_INSTRUMENTS:
            raise ValueError("Select at least one instrument or use Check all.")
        tokens = [item.strip() for item in re.split(r"[,\n]", instruments) if item.strip()]
        instrument_list = resolve_instrument_names(tokens) if tokens else None
        try:
            model = get_model(local_model_source(model_size), device, dtype)
        except LocalEntryNotFoundError as error:
            raise RuntimeError(
                f"MuScriptor {model_size} weights are not cached and Hugging Face could not be reached. "
                f"Download MuScriptor/muscriptor-{model_size} model.safetensors and config.json "
                "or choose a model size already cached on this machine."
            ) from error
        events = []
        for event in model.transcribe(audio=source, use_sampling=use_sampling, temperature=temperature,
                                      cfg_coef=cfg_coef, instruments=instrument_list, batch_size=1,
                                      no_eos_is_ok=not strict_eos, beam_size=beam_size,
                                      prelude_forcing=prelude_forcing):
            if not isinstance(event, ProgressEvent):
                events.append(event)
        notes, skipped = quantize_events(events, qpm, model._program_for_instrument, invalid_notes,
                                         decoded_beat_map)
        if skipped:
            print(f"[SKEBA MuScriptor] Skipped {skipped} malformed note(s).")
        midi = encode_midi(notes, qpm, numerator, denominator)
        folder, filename, counter, _, _ = folder_paths.get_save_image_path(filename_prefix, folder_paths.get_output_directory())
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{filename}_{counter:05}_.mid")
        with open(path, "wb") as stream:
            stream.write(midi)
        return io.NodeOutput(path, notes_to_json(notes, qpm), midi)
