# Settling frames (experimental)

`SKEBA H3 Continuation Timing` adds hidden preroll to an existing generation length. Zero preserves existing behavior. Positive values round up to multiples of 17 frames, keeping the H3 video latent cycle intact (17 frames is about 0.71 seconds at 24 fps).

Connect generation_length to the reference encoder's length, settling_frames to Motion Context's new input, and use the same first-clip/new-location bypass for both. Connect Motion Context's trim_frames to Motion Context Trim. Apply this in both passes. Existing length should already include your usual overlap; this adds only extra preroll.

The previous video guide is shifted right by the added frames. Its audio timeline guide shifts by the same amount, retaining audio-grid alignment. The visible boundary and trim move by that amount too, so delivered duration remains unchanged relative to zero settling. This is extra hidden preroll BEFORE the inherited guide, not an unconditioned gap after the previous clip's last frame. It requires head anchoring and video context. Generic audio-reference mode is not timeline-shifted.

`example/Loop_Debug_Settling.json` wires both passes and the final trim. Set settling_frames on `Settling frames - BASE (adjust here)`; the upscale timing node shares that setting. It defaults to zero. Try 17, then compare fast motion and static backgrounds using identical seeds. Extra frames cost sampling time and memory. No continuity improvement is guaranteed until render testing.

Keep previously saved context latents as the full sampler output. Do not use trimmed video to infer the original latent timeline. Existing first/last-frame constraints and explicit prompt timestamps are not rewritten by this mode; review prompt timing if it explicitly schedules actions inside the hidden region.
