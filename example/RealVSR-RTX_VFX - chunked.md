# RelayVSR / RTX chunked upscale

Restart ComfyUI and reload `RealVSR-RTX_VFX - upscale.json` from the saved workflows, or open `RealVSR-RTX_VFX - upscale - chunked.json` from these examples.

1. Click **Upload video…** on **Choose Video + Chunk Seconds** to upload and automatically select a video. Alternatively, choose an existing video from `ComfyUI/input`. Refresh node definitions if a file added outside the browser is missing.
2. Set `chunk_seconds` (default 30). Boundaries round to whole source frames; at 24 fps, 30 seconds is 720 frames. A two-minute input runs in four batches. Lower this value if one batch still exceeds memory.
3. Queue once. VHS Meta Batch Manager automatically requeues subsequent chunks and streams them into one encoder. Leave the loader's frame cap and skipped frames at zero, force rate at zero, and select-every-nth at one.
4. The final video is saved under `output/RelayVSR_Chunked/`. Audio is read from the source and muxed once at completion, preserving synchronization without separately saved audio/video chunks. VHS removes its temporary silent encode; metadata preview PNGs are disabled.

The **Frame Increase x2** value also drives **SKEBA RTX Chunk Timing**. RTX multiplier interpolation returns `(N-1)*multiplier+1` frames. Timing correction repeats its last frame `multiplier-1` times so every source frame retains its full playback duration and chunk errors do not accumulate. Keep RTX in multiplier mode. Temporal RTX/DLSS/RelayVSR state restarts per chunk; boundary appearance can differ from processing the entire video at once.

CPU integration checks exercised the installed VHS loader and encoder with a synthetic 120-second video and audio: four 720-frame batches and an uneven `[1000, 1000, 880]` split both yielded exactly 5760 frames at 48 fps, 120-second audio/video, and one final output. The expensive GPU enhancement stages were substituted during these checks; full-resolution GPU memory use still depends on source resolution and chunk duration.
