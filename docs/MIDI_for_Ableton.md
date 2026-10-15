# MuScriptor MIDI in Ableton Live

Connect `MuScriptor Transcribe Audio to MIDI.midi_path` to `SKEBA MIDI for Ableton.midi_path`. Connect `FL Audio BPM Analyzer.bpm` to the new node's `bpm` input. Feed the same source audio to both analyzers.

MuScriptor exports a multi-track MIDI at a fixed 120 BPM. The SKEBA node writes a separate MIDI file with the chosen tempo and adjusts tick positions so each note keeps its original time in seconds. The source MIDI is not changed. The default rounds BPM to two decimals; whole-BPM and exact-tempo options are also available. The node requires `mido`, installed with MuScriptor.

Import the new file into Ableton Live's Arrangement view. If Live asks whether to import the MIDI tempo, accept it for a new set or set the Live tempo to `bpm_used` yourself. Bring the original audio in at the same timeline start; keep its Warp behavior in mind when comparing alignment. The conversion does not quantize notes to the beat grid or identify the first downbeat. Check the FL BPM estimate, especially half-time or double-time results, before using it as the project tempo.
