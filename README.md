# Skeba AI Nodes for ComfyUI

Consolidated tagged references, workflow utilities, batching tools, and MiniMax
H3 Motion Context nodes for ComfyUI.

H3 Reference Library replaces a large set of manually connected reference widgets with a local media library. Add images, voice clips, descriptions, and categories once, then use semantic tags such as `{news_anchor}` or `{newsroom}` directly in a prompt.

## Features

- Local manager at `/h3-references` with a toolbar launcher and an **Open Reference Library** button on the node
- Separate known-character catalog at `/h3-built-in-references`
- Image, audio, and paired image-and-audio records
- Drag-and-drop bulk import with automatic pairing by filename stem
- Reusable tags, descriptions, searchable categories, previews, and audio playback
- Category and reference-type organization for characters, locations, objects, and music
- Category-first, reference-type-second selection guide for prompt building
- Bundled MiniMax H3 character catalog sourced from an editable Markdown file
- Searchable built-in character browser with individual and multi-tag copy
- Automatic MiniMax H3 image and audio reference ordering
- Nine image outputs and three audio outputs, matching the H3 node limits
- Direct in-place replacement of tags with their saved descriptions
- Local-only storage with no downloads, telemetry, or external requests
- Prompt and image batching, indexed selection, and video clip combining utilities
- Workflow IO tagging and named passthrough/bypass controls
- Universal lazy bypass utility with up to sixteen type-synchronized lanes

## Installation

Clone the repository into `ComfyUI/custom_nodes`:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/nikaskeba/ComfyUI-Minimax-H3-Reference-Library.git
```

Restart ComfyUI after installation. No additional Python packages are required beyond the dependencies included with ComfyUI.

## Usage

1. Add **H3 Tagged Reference Prompt** from `Skeba AI Nodes - Reference`.
2. Click **Open Reference Library** on the node or use the library button in the ComfyUI toolbar.
3. Add a tag such as `creature`, choose a category, and attach an image, audio clip, or both.
4. Enter the tag in braces in the node prompt:

```text
[Shot 1] {creature} stands at the bottom of {creepy_stairs}.
```

5. Connect `prompt` to the MiniMax H3 prompt input.
6. Connect `image_1` through `image_9` and `audio_1` through `audio_3` to the corresponding MiniMax H3 reference inputs.

![H3 Tagged Reference Prompt connected to MiniMax H3 Reference to Video](media/reference-connection.png)

The node replaces each tag in place with its assigned media slot and saved
description. Image records use `<Picture N>` and audio-only records use
`<Audio N>`. Referenced media is still loaded automatically. Explicit voice tags
receive audio slots first; remaining paired image-and-audio records are
prioritized afterward. Paired records receive picture slots before image-only
records, and every generated marker uses the resulting output socket number.

Example generated prompt:

```text
[Shot 1] <Picture 1> (a bald creature with prominent claws) stands at the bottom of <Picture 2> (a staircase with spider webs and eerie lighting).
```

The node does not prepend subject legends. Slot markers appear only where their
tags occur in the original prompt.

Use section-sign tags when a prompt needs to identify a library voice and its
audio slot:

```text
<d>[English §news_anchor§] Good evening.</d>
```

If the record supplies the first loaded audio file and has the description
`a calm broadcast voice`, the node produces:

```text
<d>[English <Audio 1> (a calm broadcast voice)] Good evening.</d>
```

A voice tag with only a description expands to that description. A voice tag
with only an audio file expands to its `<Audio N>` slot. Audio files beyond the
three H3 audio outputs do not claim a slot and fall back to their description or
plain tag name.

For paired records, picture and audio assignments remain on their respective
tag lines:

```text
{performer} -> <Picture 1> (the performer on stage)
§performer§ -> <Audio 1> (an energetic speaking voice)
```

## Built-In Characters

Add **Built-In Reference** from `Skeba AI Nodes - Reference` for characters already known by
MiniMax H3. Copy a caret tag from the separate character database, then use it
in the node prompt. The node's **Open Built-In Characters** button opens that
standalone page, which has no image or audio management controls:

```text
[Shot 1] ^Abby Sciuto^ works at her desk.
```

The node expands it to:

```text
[Shot 1] Abby Sciuto played by Pauley Perrette featured on NCIS works at her desk.
```

Built-in characters are prompt-only and do not consume image or audio reference
sockets. The catalog lives in `built_in_references.md`. Add or update Markdown
table rows there, then refresh the character catalog. Node execution tracks the
file revision automatically.

For dialogue, use a tilde voice tag:

```text
<d>[English ~George Costanza~] Damn, Jerry.</d>
```

The node expands it without the show or franchise name:

```text
<d>[English in George Costanza's voice as played by Jason Alexander] Damn, Jerry.</d>
```

When a character has multiple portrayals, the catalog supplies an actor-specific
tag such as `^Bruce Wayne / Batman | Christian Bale | The Dark Knight^`.
The character page can search and sort by character, actor, or show in either
alphabetical direction. Clip filenames remain in the Markdown source but are not
displayed or returned by the character browser API.

## Reference Library

![H3 Reference Library manager with categories, filters, and managed references](media/reference-manager.png)

The manager supports:

- Single and bulk uploads
- Matching image/audio pairing by filename stem
- Image preview and audio playback
- Search and category/media filters
- Edit, replace, and delete operations
- Existing-category dropdowns with custom category creation
- Fixed Character, Location, Object, Music, and Uncategorized reference types
- Category-first, reference-type-second library and prompt-guide grouping
- A grouped reference guide that can be copied while writing prompts

Older library records without a reference type are treated as
`uncategorized`. Their existing categories and tags remain unchanged.

Library data is stored outside the custom-node repository:

```text
ComfyUI/user/h3_reference_library/
  library.json
  images/
  audio/
```

Updating or reinstalling the custom node does not remove this library.

## Batch Text Prompt Loop

Add **Skeba Batch Text (Prompt Loop)** from `Skeba AI Nodes - Utilities` to
split a multiline prompt or another delimited string into a ComfyUI list. Its
outputs provide the prompt list, total count, one-based prompt numbers, and an
atomic `SKEBA_PROMPT_LIST` batch value.

Connect `prompt_batch` to **Skeba Select Prompt From Batch** when a workflow
needs one entry selected by index. Selection wraps around when the index is
larger than the batch, and `current_prompt` reports the selected entry's
one-based number. Existing workflows keep working because the original
`SkebaPromptLoopNode` and `SkebaPromptFromListNode` identifiers are preserved.

## Additional Skeba Utilities

The consolidated project also provides these nodes under
`Skeba AI Nodes - Utilities` while preserving their original workflow IDs:

- **Skeba Batch Images (Folder Loader)** loads a sorted folder of images as a
  ComfyUI list, with optional starting index and image limit.
- **Skeba Get Image From Batch** selects one image by a wrapping index.
- **Skeba Combine Video Clips** joins accumulated `VIDEO` values after checking
  their frame rate, dimensions, bit depth, audio sample rate, and channel layout.
- **Skeba Bypass** passes through an optional value and reports a named enabled
  state for workflows using the bundled Skeba IO-tagging frontend controls.

The IO-tagging context-menu extensions are included in this project as well, so
node input/output metadata remains available without the separate
`skeba_io_tags` custom-node package.

## H3 Motion Context

The five Motion Context nodes are available under
`Skeba AI Nodes - Motion Context` with their original workflow identifiers:

- **SKEBA H3 Motion Context** pins picture and audio context from the previous
  clip so the next MiniMax H3 generation can continue it.
- **SKEBA H3 Motion Context Trim** removes the leading pinned context frames
  from the decoded continuation.
- **SKEBA H3 Motion Context Save Latent** saves the sampler's combined video and
  audio latent for a later workflow run.
- **SKEBA H3 Motion Context Load Latent** loads that saved latent, including
  indexed loop slots.
- **SKEBA H3 Seam Exposure Match** fades an exposure correction across the
  beginning of a continuation to reduce visible brightness jumps.

The Motion Context patches install lazily on the first execution of its main
node and are gated by that node's own markers. Merely installing this package
does not patch unrelated H3 workflows. Full wiring, settings, and limitations
are documented in [`motion_context/README.md`](motion_context/README.md).

## Universal Node Bypass

Add **Universal Node Bypass** from `Skeba AI Nodes - Utilities` to switch one or
more processing branches together. For each lane, connect the unchanged source
to `original_N`, connect the processor result to `processed_N`, and connect
`output_N` to the downstream node:

```text
source -----------------------> original_1
   +----> processor ----------> processed_1

Universal Node Bypass output_1 ----> downstream node
```

The Boolean defaults to **PROCESS** (`false`), which requests and returns only
the `processed_N` inputs. **BYPASS** (`true`) requests and returns only the
`original_N` inputs. The unselected branch is lazy and may remain disconnected.
If a selected input is missing for a connected output, execution reports the
lane and socket that must be connected.

One empty lane is shown initially. Connecting its last visible lane reveals the
next lane, up to sixteen. The paired inputs and output adopt the type of their
first connection. Unused trailing lanes are hidden, while gaps between connected
lanes retain their indices when a workflow is saved and reloaded.

The utility skips a processor only when that processor's result is consumed
exclusively through this lazy switch. Any other live downstream connection can
still cause the processor to execute. All three sockets in a lane must carry a
compatible type. A type-changing processor therefore needs an `original_N`
value matching its output type; for example, an IMAGE cannot bypass directly
into a LATENT lane.

## Limits and Behavior

- One node execution supports up to nine image references.
- The first three eligible audio references are loaded; paired image/audio records receive priority.
- Every tag is replaced once in place with its saved description.
- A prompt with no tags passes through unchanged and loads no media.
- Missing tags, files, or more than nine referenced images produce a clear node error.
- Tags may contain letters, numbers, underscores, and hyphens.
- Library reference tags use `{tag}`; library voice tags use `§tag§`.
- Built-in character tags use `^Character Name^`; voice tags use `~Character Name~`.

## Updating

```bash
cd ComfyUI/custom_nodes/ComfyUI-Minimax-H3-Reference-Library
git pull
```

Restart ComfyUI after updating backend files.

## Registry Publishing

The repository includes Comfy Registry metadata and a manual GitHub Actions publishing workflow. A maintainer must:

1. Use the `nicholasskeba` publisher at [Comfy Registry](https://registry.comfy.org/).
2. Create a Registry publishing API key for that publisher.
3. Add the key to this GitHub repository as an Actions secret named `REGISTRY_ACCESS_TOKEN`.
4. Run **Publish to Comfy Registry** from the repository Actions page.

The Registry powers discovery and installation through ComfyUI-Manager. Increment the version in `pyproject.toml` before publishing each subsequent release.

## License

This combined project is licensed under GNU GPL version 3. Original MIT notices
for components that predate the Motion Context consolidation are retained under
`LICENSES/`; see `THIRD_PARTY_NOTICES.md` for provenance and modifications.

[MIT](LICENSE)
