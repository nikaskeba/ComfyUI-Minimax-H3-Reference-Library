# H3 Inpaint Source Scrub (Experimental)

The masked H3 inpaint pass normally receives the original source-video latent, including the area it is asked to regenerate. This optional node clears the selected area of that video latent before sampling. The remaining video latent, audio latent, generation mask, and other latent metadata stay intact.

Place it after `MiniMax H3 Set Generation Mask` and before `SKEBA H3 Inpaint / Audio-Driven Latent`. The [source-scrub test workflow](../example/Minimax%20-%20Inpaint%20_%20Controlnet%20-%2011_9_26%20-%20source%20scrub%20test.json) is wired this way, with `enabled=true`, `spatial_halo=1`, and `temporal_halo=0`. The original workflow is unchanged.

The mask is reduced to H3's video latent grid by selecting every latent position touched by a white source-mask area. `spatial_halo` clears additional neighboring latent cells to cover VAE spillover. `temporal_halo` clears neighboring latent time steps; start at zero and try one only if a face persists across time. A larger halo removes more source guidance and may reduce motion or background continuity.

Compare the base-pass decode before the upscale. If the original face remains even after source scrubbing, check the mask-grid preview for missing frames and test higher base-pass denoise. If the base pass is clean but the face returns after upscale, adjust the upscale pass instead. This node changes the latent presented to H3; it does not guarantee that the output face follows the prompt or references.
