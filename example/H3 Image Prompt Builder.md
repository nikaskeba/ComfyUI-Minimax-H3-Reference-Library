# H3 Image Prompt Builder

Connect **H3 Image Prompt Builder → prompt** to **H3 Image Tagged Reference Prompt → prompt**. The builder is the editing panel; the tagged-reference node supplies the rewritten prompt and up to 16 actual images.

- Search references by name/description and filter character, location, object, or clothing. Only references with an available image appear. Double-click a result or click Insert selected reference.
- Select Image Upscale or Style Enhancer, fill each replacement using a selected reference/photo or text, then click Replace prompt with template. This replaces the prompt; it does not append it.
- Add/edit templates with a name, short description, and `[[replacement]]` fields. Save the workflow to persist templates in that builder node. They are not a global template library.
- Select a photo from ComfyUI/input or upload one. Uploads are stored in `input/Skeba One-Time Photos` and inserted as `{photo:...}` tags. These files are not added to the reference library and are retained so saved workflows can run again.
- References/photos receive image slots in order of first appearance. Repeated tags reuse their slot. Keep the uploaded input files when moving/reusing the workflow.

Restart ComfyUI and refresh the browser after installing. The example JSON contains the two connected nodes; connect the resolver's prompt and image outputs to your image-generation workflow.
