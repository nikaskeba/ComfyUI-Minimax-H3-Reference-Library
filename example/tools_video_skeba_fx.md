# Skeba Video Effects

Restart ComfyUI, refresh the browser, and open `tools_video_skeba_fx.json`.
Choose/upload a video, set seconds per batch, and select an effect. Its controls
change with the selected mode. Queue once for one final video with source audio.

- **VHS / BetaMax / LaserDisc:** independent MIT-licensed copy of MiniMax-H3-Tape-FX, including its damage and OSD controls.
- **Film Grain:** grain strength, size and color contribution.
- **MiniDV:** reduced horizontal chroma detail, quantization, sensor noise and alternating-line displacement.
- **35mm to 1990s TV:** film grain, an SD-resolution transfer, chroma smear, warm color, scanlines and subtle flicker.

MiniDV and film/TV are visual approximations; they do not encode DV, change frame
rate, add telecine cadence, or change the image's aspect ratio.

**Fast** processes at up to 640 pixels on the longest edge; **Balanced** uses
1280; **Full Resolution** uses the input size. All return the original dimensions
and frame count. Faster settings also soften fine detail. Grain-only processing
is already inexpensive, so Full Resolution is useful when preserving detail matters.

The node uses the input tensor's device and adds no dependencies. Tape state and
OSD counters restart each batch. `frame_offset` advances grain/noise and film
flicker for manually chained chunks; this example leaves it at zero, so those
patterns repeat per batch. Audio passes directly to the final writer unchanged.

Local benchmark: four 720p RGB frames on CPU with four Torch threads, median of
three runs: VHS 0.101s Fast / 0.332s Full; Film Grain 0.044s / 0.055s;
35mm-to-TV 0.047s / 0.162s. These timings exclude video decoding/encoding.

The original tape node and workflow remain available. The copied engine's MIT
license and attribution are included at the top of `tape_fx_engine.py`.
