# SKEBA H3 Video to Prompt (Local VLM)

Connect a `VIDEO` source to **SKEBA H3 Video to Prompt (Local VLM)** and connect
**SKEBA H3 Local VLM Loader** to its `vlm` input. The loader lists complete
Qwen VL model folders in ComfyUI's `models/LLM`, `models/clip`, `models/vlm`,
`models/video_analyzer`, and registered extra model paths. A custom absolute
folder can be entered instead. The dropdown shows relative names such as
`Qwen-VL/Qwen3-VL-2B-Instruct`; it does not expose the Windows drive path.
The folder must contain the model weights,
`config.json`, tokenizer files, and the vision preprocessor. The VLM is loaded
with `local_files_only=True`; this loader never calls Hugging Face download.

An ordinary ComfyUI `CLIP` output is a text encoder, not a generative
vision-language model, so it cannot replace the VLM input. A single `.safetensors`
CLIP file also lacks the processor and language generator needed for this node.
The loader can *find a complete VLM stored under `models/clip`*, but it loads
that model directly from its folder rather than accepting a `CLIP` socket.

Both optional audio-analysis switches default to off. **Use ASR** and **Use
audio tags** can download their own weights when enabled; leave them off for
an entirely offline run. The video analysis supports T2VA, I2VA, FL2VA, L2VA,
Ref2VA, and LTX modes. Intermediate analysis and Ref2VA keyframes remain in
ComfyUI's `temp/skeba_h3_video_to_prompt/<run-id>/` directory.

The advanced **analysis_prompt** field displays the original video-analysis
instructions and can be edited or connected to a STRING node. It controls the
first pass that extracts shots and scene details; the mode-specific H3 rewrite
guide is unchanged. Older workflows use the original instructions by default.

Connect **Whisper + Nemotron Transcribe** `srt` to the optional `srt_subtitles`
input to supply timed dialogue and speaker labels. Connected SRT takes precedence
over this node's ASR switch; the VLM still analyzes video frames and uses the
subtitles in both its shot analysis and final prompt rewrite. Speaker labels are
kept distinct, while visual identity is assigned only when the frames support it.
SRT timestamps refer to the source video's timeline. The parsed cues are saved
in the run's `transcript.txt` for inspection.

Select **SKEBA Tagged** to produce an editable five-section prompt with
`subject_definitions`, `summary`, `detailed_description`, `overall_soundscape`,
and `non_diegetic_music`. It uses the VLM's observed shot starts and style, and
puts each SRT dialogue event into its own `[Shot N: Xs]` entry. Visual subjects
become numbered `<Subject N>` definitions, and C1/C2 labels are replaced
throughout the shot text. An SRT voice is linked to one of those subjects only
when the analysis explicitly names that visual subject for a matching timed
speaker event. Otherwise it receives a temporary `<character:speaker_XX>` tag
to resolve after checking the video. These numbered subjects are editable text
placeholders, not automatically attached image or audio references. Set
`location_reference` to an existing
tag such as `{10_forward_bar}` if desired; otherwise the node makes a temporary
location definition from the visual analysis. This mode requires an SRT input
and uses a deterministic formatter after visual analysis instead of the normal
H3 rewrite pass. SRT has no language field, so dialogue defaults to `[English]`.

`pipeline.py`, `vlm.py`, and the prompt guides are adapted from
[ComfyUI-VideoAnalyzer](https://github.com/aroslanov/ComfyUI-VideoAnalyzer).
Their MIT license and third-party notices are retained in [LICENSE](LICENSE).
