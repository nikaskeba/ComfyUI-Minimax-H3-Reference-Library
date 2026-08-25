# H3 Reference Library for ComfyUI

Reusable tagged image and audio references for MiniMax H3 Reference to Video workflows.

H3 Reference Library replaces a large set of manually connected reference widgets with a local media library. Add images, voice clips, descriptions, and categories once, then use semantic tags such as `{news_anchor}` or `{newsroom}` directly in a prompt.

## Features

- Local manager at `/h3-references` with a toolbar launcher and an **Open Reference Library** button on the node
- Separate known-character catalog at `/h3-built-in-references`
- Image, audio, and paired image-and-audio records
- Drag-and-drop bulk import with automatic pairing by filename stem
- Reusable tags, descriptions, searchable categories, previews, and audio playback
- Category-grouped reference selection guide for prompt building
- Bundled MiniMax H3 character catalog sourced from an editable Markdown file
- Searchable built-in character browser with individual and multi-tag copy
- Automatic MiniMax H3 subject, image, and audio reference ordering
- Nine image outputs and three audio outputs, matching the H3 node limits
- Graceful voice-description fallback when a prompt uses more than three voiced characters
- Local-only storage with no downloads, telemetry, or external requests

## Installation

Clone the repository into `ComfyUI/custom_nodes`:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/nikaskeba/ComfyUI-Minimax-H3-Reference-Library.git
```

Restart ComfyUI after installation. No additional Python packages are required beyond the dependencies included with ComfyUI.

## Usage

1. Add **H3 Tagged Reference Prompt** from `video/text`.
2. Click **Open Reference Library** on the node or use the library button in the ComfyUI toolbar.
3. Add a tag such as `creature`, choose a category, and attach an image, audio clip, or both.
4. Enter the tag in braces in the node prompt:

```text
[Shot 1] {creature} stands at the bottom of {creepy_stairs}.
```

5. Connect `prompt` to the MiniMax H3 prompt input.
6. Connect `image_1` through `image_9` and `audio_1` through `audio_3` to the corresponding MiniMax H3 reference inputs.

![H3 Tagged Reference Prompt connected to MiniMax H3 Reference to Video](media/reference-connection.png)

The node resolves references in first-use order. Records containing both image and audio are prioritized before image-only and standalone-audio records.

Example generated prompt:

```text
<Subject 1> (S1) is defined by the first reference image: a bald creature with prominent claws. <Audio 1> is the voice-timbre reference for <Subject 1> (S1): a creepy voice.
<Subject 2> is defined by the second reference image: a staircase with spider webs and eerie lighting.

[Shot 1] <Subject 1> (S1) stands at the bottom of <Subject 2>.
```

When more than three paired voices are used, later characters retain their image reference and receive a text description instead of an unavailable audio socket:

```text
<Subject 4> (S4) is defined by the fourth reference image: a reporter wearing a gray suit. <Subject 4> (S4) speaks with a calm American voice.
```

## Built-In Characters

Add **Built-In Reference** from `video/text` for characters already known by
MiniMax H3. Copy a caret tag from the separate character database, then use it
in the node prompt. The node's **Open Built-In Characters** button opens that
standalone page, which has no image or audio management controls:

```text
[Shot 1] ^Abby Sciuto^ works at her desk.
```

The node expands it to:

```text
[Shot 1] **Abby Sciuto** played by Pauley Perrette featured on NCIS works at her desk.
```

Built-in characters are prompt-only and do not consume image or audio reference
sockets. The catalog lives in `built_in_references.md`. Add or update Markdown
table rows there, then refresh the character catalog. Node execution tracks the
file revision automatically.

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
- A category-grouped reference guide that can be copied while writing prompts

Library data is stored outside the custom-node repository:

```text
ComfyUI/user/h3_reference_library/
  library.json
  images/
  audio/
```

Updating or reinstalling the custom node does not remove this library.

## Limits and Behavior

- One node execution supports up to nine image references.
- The first three eligible audio references are loaded; paired image/audio records receive priority.
- Additional paired voices are represented by their written voice descriptions.
- A prompt with no tags passes through unchanged and loads no media.
- Missing tags, files, or more than nine referenced images produce a clear node error.
- Tags may contain letters, numbers, underscores, and hyphens.
- Built-in tags use the separate `^Character Name^` syntax.

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

[MIT](LICENSE)
