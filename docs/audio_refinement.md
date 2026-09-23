# Optional H3 audio refinement

Add **SKEBA H3 Audio Refine (Optional)** from **Skeba AI Nodes - Reference / Experimental**.
This experimental extra sampling pass refines generated audio while keeping the video latent unchanged.
It is disabled by default. Switching `enabled` off (or `audio_denoise` to zero) returns the original latent without sampling or requesting the refinement model branch.

## Wiring

```text
Final upscale sampler LATENT → Audio Refine.latent → existing AV decode → trimming/save
H3 MODEL before Turbo LoRA  → Audio Refine.model
Final pass positive/negative conditioning → Audio Refine.positive/negative
RandomNoise NOISE output → Audio Refine.noise (optional)
```

Use the conditioning for that same pass, including its references and connector guidance.
Connect RandomNoise's output to **noise**, not **seed**: its output is a NOISE object, not a number. When connected, the noise source supplies both refinement noise and its seed, overriding the numeric seed widget. Without it, use the seed widget or connect an INT seed source. Off does not request the optional noise branch.
For a single-pass workflow, place refinement after that sampler instead.
Keep the latent packed as H3 video + audio; do not connect decoded AUDIO.
Existing workflows are not rewired automatically.

Standard ComfyUI samplers retain the AV Connector's `noise_mask`. Refinement keeps its protected audio regions and freezes all video. If another node removes the mask, connect the **same pass's AV Connector latent before sampling** to the optional `boundary_latent` input. This supplies protection only; audio values come from the sampled input. Different-length/trimmed boundary latents are rejected. Without either mask, all audio is eligible for refinement.

Start with **enabled on, 4 steps, audio_denoise 0.3, CFG 1, Euler / simple**. Keep the generation and refinement seeds fixed for comparisons. Try 6 steps / 0.5 separately if needed. Higher denoise can change words, voice identity, music, and timing; this is not a transparent audio filter. Protected latent values remain exact, but audio VAE decoding can still affect the audible transition around a boundary.

Compare off/on over a sequence longer than 90 seconds. Check dialogue, voice ownership, mechanical noise and joins independently. Each step still runs the joint H3 model and adds time. No frozen-video cache, dependencies, downloads, or model patches are added by this node.

For continuation experiments, choose deliberately whether subsequent context is taken from the refined output. Refining only the saved clip does not change an earlier continuation-cache branch. Playlist registration retains a connected refinement node as part of its captured generation graph; register/update again after changing the graph. The refinement seed is a separate setting captured in that snapshot; the playlist's generation seed does not automatically replace it.

Adapted from [ComfyUI-H3-AudioRefine](https://github.com/Adudeguyman/ComfyUI-H3-AudioRefine), with existing boundary-mask protection and exact off behavior. See `LICENSES/ComfyUI-H3-AudioRefine.txt`.
