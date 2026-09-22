# Tagged RefMods

RefMods can now supply appearance and/or voice for existing saved entries and built-in characters. Tags stay `{Character}` and `§Character§`. Existing records continue to use their ordinary attachments until switched.

## Library

In **Edit reference**, beneath Tag, Reference type and Library category, switch between **Standard Reference** and **RefMod**. Both sets of attachments remain saved. Standard Reference uses ordinary media. The RefMod tab shows independent appearance and voice source selectors, allowing a RefMod appearance with an ordinary voice, or vice versa. Select an attachment and save the record. Returning to Standard Reference disables RefMod sourcing without deleting the selected files.

Built-in characters have a **RefMods / sources** button. Both galleries have a RefMod attachment filter. The picker searches ComfyUI's registered `refmods` folders (including extra model paths) and `models/refmods`. It lists individual safetensors and members of bundles, with kind, token count and a sidecar image preview when available. A bundle's preview represents the bundle, not necessarily the chosen member. Missing or incompatible selected attachments fail clearly; the compiler never silently falls back to ordinary media.

Appearance accepts image/video RefMods. Voice accepts audio RefMods. A character's visual presence alone does not select its voice. Use its matching voice tag for spoken dialogue.

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

Open **RefMods** in the reference library, or `/h3-refmods`. Character editors now only select saved attachments; their Studio link opens creation separately.

- Upload several images, videos and/or audio clips. Reorder or remove sources; trim video/audio with start/end seconds (end 0 uses the remainder).
- Choose **Full reference encoding** or **Compressed reference + refinement**. Compressed mode pools the visual latent and optimizes that smaller latent against the full encode, using Fantastic's approach. It does not train a diffusion model or LoRA.
- Set the visual short edge, compressed grid and refinement steps, video frame count, and new-audio duration. Video is sampled at 24 fps and trimmed to H3's valid frame grid. Multiple visual sources share the first source's aspect; full mode center-crops later sources to that canvas.
- Select an H3 video VAE for visual uploads and an H3 audio VAE for audio uploads. Video soundtracks are not automatically used as voices; upload the desired audio track explicitly.
- Click **Train / Encode & Save**. It queues a local ComfyUI job, and the page resumes watching that job after a reload.

Visual sources are stacked into one appearance RefMod. Audio clips are joined into one voice RefMod. A combined appearance/voice asset is one `.safetensors` bundle with independently selectable members. Files are saved under a registered `refmods` folder; metadata and settings are embedded in the safetensors header, with a visual preview alongside it. Original uploads remain under `ComfyUI/input/skeba_refmod_sources`.

The RefMods tab shares the reference-library header. Thumbnail cards group bundle channels and matching `_visual`/`_audio` files, showing tokens, dimensions, duration and characteristics. Use folder filters, search and **Edit** to open an item. You can change its name/description, reorder or omit stored visual latent frames, append new visual sources, replace appearance, and keep/append/replace/remove audio. Existing frames are retained without decode/re-encode. New-source training settings do not retrain stored frames unless **Recompress / refine kept frames** is enabled. This refines against the stored latent; upload original sources for a fresh encode. Unedited bundle members are preserved.

Use **Generate previews** with matching H3 VAEs to decode stored-frame thumbnails and playable audio. Checkboxes omit frames or voice; drag or use Up/Down to reorder frames. Editing paired standalone files now saves one combined bundle (for example `actor.safetensors`). Original paired files are preserved so existing attachments remain usable; select the new bundle members on characters before deleting the old pair. An existing destination is never silently overwritten.

Editing updates the existing asset by default. Enable **Save as a copy** to create a separate `_edited.safetensors` file. Changes that would silently renumber existing attachments require saving a copy. Library cards include **Delete**, with confirmation listing the files. Deleting removes all members of selected files; source media and thumbnails remain. Existing character attachments must be reassigned if their file is deleted. Metadata/frame-only edits require no VAE. The original **SKEBA Create H3 RefMod** node remains available for existing workflows; the Studio uses **SKEBA RefMod Studio Create / Edit**.

After saving, return to the character editor, click **Refresh attachments**, select the appearance and/or audio member, and save the character. Voice-isolation guarantees and continuation behavior are unchanged; assess reference quality through render tests.

VAE dropdowns are saved as browser defaults and survive new-item creation and page reloads. They remain changeable. Gallery thumbnails prefer an exact sidecar (such as `celestial_visual.png`), then a shared pair image (`celestial.png` for `celestial_visual.safetensors` and `celestial_audio.safetensors`). PNG, JPG, JPEG and WebP are supported.

For uploaded videos, **Edit sections** opens a large preview with a scrubber, frame stepping, start/end controls and section playback. Add, reorder or remove multiple sections from the same upload. Each section has its own drawn crop and mirror setting; Apply saves selections, Cancel discards changes. Sections encode separately in listed order, with the clip-frame setting applied to each. Crops use the mirrored picture coordinates when mirroring is enabled.

New video uploads include voice by default. Use **Include Voice** on a video source to enable or disable encoding its soundtrack using the selected audio VAE. Audio uses each selected section’s start/end, joins in section order, and follows the new-voice duration cap. Existing voice can be replaced or appended using Voice edit. Previously saved visual-only latents cannot recover their soundtrack; add the original source again.

New RefMods default to Full reference. New/copy filenames derive from the Name field (copies get `_copy`); editing keeps existing filenames and attachments stable. Processing shows a queued/running indicator and elapsed time; this is not a percentage estimate.

## Direct RefMod tags

Use `{celestial_rm}` for appearance and `§celestial_rm§` inside dialogue for voice, without creating a character entry. The name comes from `celestial.safetensors` or the paired `celestial_visual.safetensors` / `celestial_audio.safetensors`. Include `{celestial_rm}` in subject_definitions as usual. A silent appearance tag does not load its voice. Use `{folder/celestial_rm}` (and matching voice tag) when filenames repeat across folders. Existing saved tags take precedence. Bundles with multiple members for the same channel require an explicit library attachment.
