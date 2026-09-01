# Skeba AI Nodes for ComfyUI

Consolidated tagged references, workflow utilities, batching tools, and MiniMax
H3 Motion Context nodes for ComfyUI.

H3 Reference Library replaces a large set of manually connected reference widgets with a local media library. Add images, videos, voice clips, descriptions, and categories once, then use semantic tags such as `{news_anchor}` or `{newsroom}` directly in a prompt.

## Features

- Local manager at `/h3-references` with a toolbar launcher and an **Open Reference Library** button on the node
- Separate known-character catalog at `/h3-built-in-references`
- Image, audio, and video records; embedded video soundtracks are detected automatically
- Drag-and-drop bulk import with automatic image/audio/video pairing by filename stem
- Reusable tags, descriptions, searchable categories, previews, and audio playback
- Category and reference-type organization for characters, locations, objects, music, and video
- Reference-type-aware media fields for characters, locations, objects, music, and video
- Category-first, reference-type-second selection guide for prompt building
- Bundled MiniMax H3 character catalog sourced from an editable Markdown file
- Searchable built-in character browser with individual and multi-tag copy
- Automatic MiniMax H3 image, video, video-audio, and standalone-audio reference ordering
- Nine image outputs, three standalone audio outputs, three video frame outputs, and three matching video-audio outputs
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
3. Add a tag such as `creature`, choose its reference type and category, then attach the media allowed by that type.
4. Enter the tag in braces in the node prompt:

```text
[Shot 1] {creature} stands at the bottom of {creepy_stairs}.
```

Tags entered with spaces or punctuation are normalized automatically. For
example, `Simpsons chalkboard` is saved as `Simpsons_chalkboard`.

5. Set `video_fps` if the scene's video references should use a rate other than the 24 FPS default. This one value applies to every video loaded by that node execution.
6. Connect `prompt` and the reference outputs to the MiniMax H3 node as described below.

![H3 Tagged Reference Prompt connected to MiniMax H3 Reference to Video](media/reference-connection.png)

The node replaces each tag in place with its assigned media slot and saved
description. Image records use `<Picture N>`, video records use `<Video N>`, and
audio-only records use `<Audio N>`. Videos are decoded into IMAGE frame batches.
The node's single `video_fps` setting resamples every video used in that execution
to one common rate; it defaults to 24 FPS and accepts values from 1 through 240.
Embedded video soundtracks are returned independently as AUDIO, while silent
videos leave their matching audio output empty.

Explicit voice tags receive standalone audio slots first. Remaining paired
image-and-audio records are prioritized afterward. Paired records receive
picture slots before image-only records, and every generated marker uses the
resulting output socket number.

### H3 Tagged Reference Prompt inputs and outputs

| Socket/widget | Type | Behavior |
| --- | --- | --- |
| `prompt_template` | STRING | Prompt containing library reference and voice tags. |
| `video_fps` | FLOAT | One forced frame rate for all videos loaded by this node; default `24`, range `1`–`240`. |
| `prompt` | STRING | Rewritten prompt containing the assigned H3 slot markers. |
| `mapping` | STRING | Human-readable tag-to-slot mapping for the current prompt. |
| `image_1` … `image_9` | IMAGE | Ordered still-image references. |
| `audio_1` … `audio_3` | AUDIO | Ordered standalone or paired audio references. |
| `video_1` … `video_3` | IMAGE | Ordered video references decoded as frame batches. |
| `video_audio_1` … `video_audio_3` | AUDIO | Soundtrack aligned to the corresponding video output, or empty for a silent video. |

The video sockets were appended after the original image and audio sockets so
saved workflows retain the existing output indices.

Wire the video outputs as follows:

| Reference node output | MiniMax H3 input |
| --- | --- |
| `video_1` | `ref_video_0` |
| `video_2` | `ref_video_1` |
| `video_3` | `ref_video_2` |
| `video_audio_1` | `ref_video_audio_0` |
| `video_audio_2` | `ref_video_audio_1` |
| `video_audio_3` | `ref_video_audio_2` |

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

- Single and bulk image, audio, and video uploads
- Matching image/audio/video pairing by filename stem
- Bulk-import image thumbnails, first-frame video previews, and playable audio previews
- Existing-category dropdowns, custom category creation, and per-media descriptions
- Media-aware reference-type choices that hide unsupported types and media fields
- A prominent **Add Audio Track** / **Replace Audio Track** control for bulk character and object setup
- Automatic Video type selection for video-only bulk drafts
- Automatic normalization of readable tags such as `Simpsons chalkboard` to `Simpsons_chalkboard`
- Persistent single-record, bulk-banner, and per-draft upload errors with backend or proxy response details
- Safe partial bulk imports: successfully imported drafts are removed so retrying a failed batch does not duplicate them
- Image and video preview plus audio playback
- Search and category/media filters
- Edit, replace, and delete operations
- Category-first, reference-type-second library and prompt-guide grouping
- A grouped reference guide that can be copied while writing prompts

Reference type controls which media can be attached:

| Reference type | Allowed library media | Bulk-import behavior |
| --- | --- | --- |
| Character | Image and optional audio | Image and voice descriptions are shown; an audio track can be attached directly to an image draft. |
| Location | Image only | Only the image and its description are shown. |
| Object | Image and optional audio | Image and audio descriptions are shown; an audio track can be attached directly to an image draft. |
| Music | Audio only | Only the audio file and audio description are shown. |
| Video | Video only | Selected automatically for a video-only draft; the first frame is previewed. Embedded audio is detected automatically. |

Bulk reference-type choices are filtered by the files already attached. For
example, an image draft offers Character, Location, and Object; after audio is
attached it offers only Character and Object. Unsupported empty rows such as
`Video: None` are hidden.

Older records without a reference type remain `uncategorized` for backward
compatibility. Uncategorized stays selected while editing such a record but is
hidden from new reference-type choices. Existing categories, tags, and media
remain unchanged until the record is deliberately reclassified.

Library data is stored outside the custom-node repository:

```text
ComfyUI/user/h3_reference_library/
  library.json
  images/
  audio/
  videos/
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
- One node execution supports up to three reference videos and their three slot-aligned soundtracks. Videos without audio remain valid.
- The node-level `video_fps` value applies to every referenced video in that execution; frame rate is not stored per library clip.
- Reference videos are returned as IMAGE frame batches, and their embedded soundtracks are returned separately as AUDIO.
- Every tag is replaced once in place with its saved description.
- A prompt with no tags passes through unchanged and loads no media.
- Missing tags, files, excessive reference counts, and invalid selected media produce actionable errors.
- Upload failures remain visible in the editor or affected bulk draft instead of appearing only in the browser console.
- Stored tags contain letters, numbers, underscores, and hyphens; spaces and punctuation entered in the manager are normalized automatically.
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
