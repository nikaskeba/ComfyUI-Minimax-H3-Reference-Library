# DaSiWa upscale after H3 video/audio inpainting

Open `example/video_audio_inpaint_alt_upscaler_fixed.json` after restarting ComfyUI. The uploaded `video_audio_inpaint_alt_upscaler.json` is unchanged.

DaSiWa rejects any input latent carrying a `noise_mask`. ComfyUI's `SamplerCustomAdvanced` copies the base inpaint mask into both latent outputs even after sampling has finished. The new **SKEBA H3 Finish Inpaint Latent** node removes only that stale mask after the base sampler. It preserves the completed video and audio tensors and all other latent metadata.

DaSiWa performs both the latent enlargement and its own four-step, 0.2-denoise tiled video diffusion. It preserves audio internally. The original graph fed that completed output into another `SamplerCustomAdvanced` at 0.4 denoise, potentially changing faces again. The fixed graph sends DaSiWa's completed output directly to the existing final decode/save path. The old second sampler remains visibly labeled unused for comparison and does not feed any output. A display shows DaSiWa's execution plan.

This is a graph and metadata fix. Unit tests confirm mask removal and the final graph routing, but the DaSiWa model has not been rendered locally. If a subsequent runtime error occurs, preserve its full stack trace; the next likely checks in DaSiWa are native H3 model type, a model wrapper, and conditioning controls.

## Optional context guides

The fixed graph now routes the cached reference conditioning through **SKEBA H3 Upscale Context Guides** before DaSiWa. Its **Off / Automatic sparse** choice defaults to **Off**, which passes the original conditioning through unchanged. **Automatic sparse** decodes the *same completed base-pass latent* sent to DaSiWa and adds two single-frame guides at roughly one-third and two-thirds of the clip. It skips a position already occupied by an existing H3 keyframe. The reference assets and audio path stay unchanged.

For comparison, keep the base generation and upscale noise seed fixed. First compare Off with Automatic sparse at the existing 0.2 denoise. If the returning face still shifts, compare 0.1 denoise, then temporal chunking off if memory permits. Extra guides can help a cut but can also soften detail or restrain motion; inspect the whole clip before keeping the option on. This node does not repair a face that already changed in the base-pass decode.
