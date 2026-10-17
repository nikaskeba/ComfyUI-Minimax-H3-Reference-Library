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

`pipeline.py`, `vlm.py`, and the prompt guides are adapted from
[ComfyUI-VideoAnalyzer](https://github.com/aroslanov/ComfyUI-VideoAnalyzer).
Their MIT license and third-party notices are retained in [LICENSE](LICENSE).
