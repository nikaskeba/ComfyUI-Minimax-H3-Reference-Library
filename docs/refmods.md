# Tagged RefMods

RefMods have their own gallery. Selecting a RefMod also adds its direct appearance and voice tags to the shared **Reference creator** alongside standard references and built-in characters. **Copy guide** in Reference creator copies the combined selection. Selections persist when navigating between library pages and synchronize across open tabs; Clear selection in Reference creator clears all three sources. The RefMod page also provides a guide for just its selected RefMods.

## Library

Cards show a thumbnail, name and actions. Technical information (tokens, encoding mode, audio length and paired filenames) is collapsed under **Details**. **Select** toggles membership in the RefMod prompt guide, retained in this browser across reloads.

RefMod **Category** is descriptive: character, location, object, music or video. It does not change encoding or tag behavior. **Collection** is optional and shares the reference library's category/collection names. Built-in characters also have an optional collection field. A saved name becomes available across all three galleries; refresh an already-open gallery to update its choices.

RefMod attachment controls have been removed from the standard and built-in character editors. New RefMod usage is through direct `_rm` tags in the separate gallery. Existing saved RefMod assignments remain supported for older workflows; this UI change does not delete attachments or files.

**Export** saves a portable `.safetensors` file with all members and category/collection metadata. Paired appearance/audio files become a single bundle without re-encoding. Chrome's save picker lets you choose the destination; browsers without that API use their normal download flow. Exported files can be added elsewhere with **Import RefMods**. Existing source files remain unchanged.

Appearance accepts image/video RefMods and voice accepts audio RefMods. Visual presence alone does not select voice; use the matching voice tag for dialogue. Discovery uses registered `refmods` folders, including extra model paths, and `models/refmods`.

## Wiring

Use **SKEBA Apply H3 RefMod** from **Skeba AI Nodes - Reference**:

```text
H3 Tagged Reference Prompt.reference_bundle -> SKEBA Cached Reference Encoder.reference_bundle
H3 Tagged Reference Prompt.mods -> SKEBA Apply H3 RefMod.mods
Cached Reference Encoder.positive -> SKEBA Apply H3 RefMod.conditioning
Apply.conditioning -> AV Connector (if used) -> Motion Context -> Guider
```

Repeat this arrangement for both passes. `mods` is appended after `reference_bundle`; existing output indices remain unchanged. When selected RefMods are present, the prompt node uses bundle-only loading for all references. Ordinary media and RefMods are numbered together in actual encoder order. Do not use the raw sockets to encode a RefMod prompt with the stock encoder.

`example/workflow_sep15_refmods.json` is a separate copy of the disk/playlist workflow with Apply inserted in both passes. Existing examples are unchanged. Select your own library RefMods before testing; no assets are bundled.

## Apply and ownership

The self-contained Apply node supports external `H3_REF_MODS` stacks as well as tagged bundles. No sibling custom-node package is imported at runtime. MIT notices for the adapted Fantastic runtime and MiniMaxH3Mod Apply/graph code are in `LICENSES`.

Controls retain upstream defaults and precedence: graph preset overrides widget curves; with override enabled, the first valid saved curve/config overrides the curve and its saved retention when present. The curve graph output and PNG preset saving are included. Retention changes reference strength; curves act across the reference's own latent frames, not output-video timing.

For tagged bundles, Apply updates matching prepared conditioning blocks in place. Reapplying does not duplicate references or compound weakening. Ordinary references, keyframes and other conditioning fields survive unchanged. Mismatched bundles, block removal through zero retention, and scrambling/subsetting of multiple numbered blocks are rejected. Leave scramble seed at `-1` for tagged references. External unbound stacks retain append, deterministic shuffle/subset, curves and token-budget behavior.

Visual RefMods can exceed the ordinary three-video socket limit through the bundle. Ordinary media socket limits and the maximum of three standalone audio references still apply. One RefMod per entry/channel is supported; duplicate-copy weighting is not included.

## Voice budget and caching

The existing optional auto-crop setting shares 15 seconds across the selected character voices: 15 / 7.5 / 5 seconds for one / two / three. Repeated tags count once, silent and text-only characters do not count, and short clips do not redistribute their unused time. Ordinary and RefMod voices share this budget.

A RefMod voice that needs cropping is decoded, cropped from sample zero with the shared waveform helper and encoded with the connected audio VAE. Apply uses that prepared latent, preserving the crop. Short RefMods retain their stored latent. Explicit audio reuse and non-character audio remain outside the voice budget. Mixed references can still exceed the overall model audio allowance.

Visual RefMods are decoded for Qwen text-encoder presentation, while their saved latents supply the model reference blocks. Prepared results are cached with source content, sidecar metadata, bundle member, channel, VAE/encoder identity and processing/crop settings. Unknown model identity disables persistent reuse. Mapping and cache status report the selected voice cap.

## RefMod Studio: create, train, save and edit

Open **RefMods** in the reference library, or `/h3-refmods`. Use **Import RefMods** to select existing `.safetensors` files, including standalone appearance/audio pairs and bundles. Include matching JSON metadata and thumbnails if they are separate files. Imports are validated and copied to a unique `imports/` folder in the registered RefMod directory; originals and existing library files are not overwritten.

- Upload several images, videos and audio clips. Reorder or remove sources. Use **Edit sections** to view a video and select one or several ranges.
- Stored content shows **Voice** first, followed by **Frames**. Remove or restore individual frames, remove all frames, or remove/restore the stored voice. Kept content precedes added sources. To replace appearance or voice, remove the old source first. Removing a bundle member that would renumber attached references requires **Save as a copy**, preserving existing character attachments.
- **Max video length per section (seconds)** limits each newly added video section, converted at 24 FPS and fitted to H3's frame grid. **Max voice length (seconds)** caps the combined kept and added voice from its beginning. These controls do not stretch or pad short sources. Stored visual frames stay unchanged unless removed or explicitly recompressed.
- Full reference mode is the default. Compressed mode pools the visual latent and optionally refines it; it does not train a model or LoRA.
- Connect your workflow's video/audio VAEs to **SKEBA RefMod Studio Create / Edit**, then click its **Open RefMod Library** button. Encoding and preview jobs use those exact connected loader branches, including their settings. The workflow must remain open in the same browser while requesting a job. With multiple Studio nodes or ComfyUI tabs, opening from the intended node selects the correct connections. No separate browser VAE defaults are used.
- Keeping, reordering and metadata-only edits need no VAE. A queued job includes only the necessary connected VAE dependencies and the Studio operation, not unrelated generation/output nodes.
- **Cancel editing ×** clears the unsaved edit and returns to the library. It does not delete an asset. It is disabled while processing a job.
- Updating a bundle retains its format. Appearance and voice are saved in one safetensors file. Adding a second channel to an existing standalone file requires a copy so existing attachments are not silently changed.

Restart ComfyUI and refresh the browser after updating. Encoding/preview jobs appear in ComfyUI's queue; the page shows queued/running/completed status and recovers pending jobs after refresh.

## Direct RefMod tags

Use `{celestial_rm}` for appearance and `§celestial_rm§` inside dialogue for voice, without creating a character entry. The name comes from `celestial.safetensors` or the paired `celestial_visual.safetensors` / `celestial_audio.safetensors`. Include `{celestial_rm}` in subject_definitions as usual. A silent appearance tag does not load its voice. Use `{folder/celestial_rm}` (and matching voice tag) when filenames repeat across folders. Existing saved tags take precedence. Bundles with multiple members for the same channel require an explicit library attachment.
