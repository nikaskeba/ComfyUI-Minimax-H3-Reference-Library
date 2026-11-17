# SKEBA SoulX-FlashHead Sampler (Frames)

Use this sampler when the subject is already framed in a 512 × 512 image and you want the generated frames directly. It uses the installed RunningHub SoulX-FlashHead loader and inference backend, with the same seed, image, audio, width, and height inputs as its sampler. It does not write an MP4 during sampling.

Connect `RunningHub SoulX-FlashHead Loader` to `pipeline`, a ComfyUI `AUDIO` track to `ref_audio`, and the square subject image to `avatar_image`. The outputs are `frames` (`IMAGE` batch), matching original `audio` (`AUDIO`), and `fps` (`FLOAT`, normally 25). Connect `frames` directly to image processing, face compositing, or a video creation node; use `audio` and `fps` when creating a video.

Only the first image in the input batch is used, matching the upstream sampler's single-avatar behavior. The audio is converted to mono for FlashHead inference. The returned audio keeps its input channels and sample rate, trimmed to the generated frame duration. FlashHead generates whole chunks, so a short trailing portion of input audio may be omitted. The number of frames and output FPS determine the exact resulting duration.

The installed `ComfyUI_RH_FlashHead` pack and its model are still required. This node avoids the intermediate H.264/AAC encode and decode; it does not change FlashHead's model or generation quality. Restart ComfyUI after adding the Skeba node.

## Square crop and return to canvas

[`talkingavatarbbox_square.json`](../example/talkingavatarbbox_square.json) demonstrates the still-image newscaster path. SAM3 supplies a bounding box. **SKEBA Avatar Square Crop (512)** expands its shorter dimension to form a square around the person, shifts the square inside the source canvas, and resizes it to 512 × 512 with no black padding. FlashHead animates that square. **SKEBA Avatar Square Composite** resizes the result back to the saved crop position and blends only the inside edge into the original full-size image. Its `edge_feather` control defaults to 12 source pixels; set it to zero to inspect the exact square boundary.

If a detected box exceeds the shorter dimension of the source image, no square inside the canvas can contain the whole box. The crop uses the largest possible square and may clip part of that subject. This path keeps the original image outside the square; movement inside the square can still make the join visible, especially if clothing or background changes near its edge.
