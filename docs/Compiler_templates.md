# H3 compiler wording templates

Add **SKEBA H3 Compiler Templates**, edit its grouped fields, and connect `compiler_templates` to both **H3 Tagged Reference Prompt** and **SKEBA H3 Prompt List Validator**. Use deterministic mode. The companion node outputs a STRING and preserves its fields in the workflow; Reset to defaults resets all groups.

Click **Import template JSON** to paste a JSON object or choose a local `.json` file, then click **Apply imported templates**. For a one-time import, `{"templates":{"dialogue_binding_reference":"..."}}` is enough; `"version":1` is also accepted. Named fields are populated and remain editable in the node. Fields missing from the import keep their current text, including deliberate empty strings. Reset to defaults first if you want all unspecified fields to return to defaults. Import checks the complete JSON, field names, text values, and placeholders before changing anything; an error leaves the current fields untouched. Save the workflow to keep the populated fields.

No connection (or a blank string) preserves existing wording. A script or any STRING node can provide partial overrides:

```json
{
  "version": 1,
  "templates": {
    "voice_reference": "[[audio]] is the voice reference for [[subject]][[speaker]].",
    "voice_characteristics": " Voice characteristics: [[voice_description]]",
    "global_binding": ""
  }
}
```

Missing keys inherit defaults; an empty field suppresses only that phrase. For example, suppressing `voice_reference` does not suppress `voice_exclusive_reference` or `voice_characteristics`. Existing mode switches still gate applicable phrases. Legacy mode ignores templates. Use the same template string on validation and generation.

Placeholders are literal, single-pass substitutions, not code. `subject`, `picture`, `video`, and `audio` supply complete numbered labels. `speaker` supplies a leading space and `(Sx)`, or an empty string. `identity` supplies `<Subject N> (Sx)`. `name` is the resolved character name. Voice descriptions retain existing sentence punctuation normalization. `description` in video/audio-media templates includes its optional leading space; in subject templates it contains the assembled name/media/appearance text. `appearances` includes the optional leading space and parentheses; `shots` contains comma-separated shot labels. `bindings` contains the resolved ownership list; `task_prefix` includes brackets. Keep intentional spaces and punctuation in the template.

Authored content and all six section headings remain outside template control. Templates do not change source assets, speaker order, numbering, cropping, RefMod injection, or continuation. Diagnostics include the effective template version and hash. Invalid JSON, unknown keys/placeholders and unsupported versions report `COMPILER_TEMPLATE` errors; final compiled output still undergoes normal reference validation.

### Shared placeholders and separate identity parts

Every template box accepts the full placeholder vocabulary. Values come from the reference currently being rendered; missing values expand to empty text. Global templates (`global_binding`, `summary_task_prefix`, `summary_editing`) have no individual character and do not borrow one. Computed local fragments such as `phrase`, `shots`, and `appearances` are available where that fragment is being assembled; elsewhere they are empty. `bindings`, `sources`, and `task_prefix` are available across fields.

| Placeholder | Example |
|---|---|
| `[[identity]]` | `<Subject 1> (S2)` |
| `[[subject]]` | `<Subject 1>` |
| `[[subject_label]]` | `Subject 1` |
| `[[subject_number]]` | `1` |
| `[[speaker]]` | ` (S2)` (leading space retained) |
| `[[speaker_id]]` | `S2` |
| `[[speaker_tag]]` | `<S2>` (optional custom notation) |
| `[[speaker_number]]` | `2` |
| `[[audio]]` | `<Audio 1>` |
| `[[name]]` | Resolved character name |
| `[[voice_description]]` | Saved voice description, with sentence punctuation |

Subject, speaker, and audio numbers remain independent. The default speaker notation remains `(S2)`; custom notation does not change binding. Audio placeholders stay empty for silent characters or characters without selected audio. Voice descriptions can now be used in retention, summaries, dialogue bindings, and subject/media definitions, not just the voice-characteristics field.

For **retention voice reference**, for example:

```text
[[audio]]: reference - the target speaker [[subject]] ([[speaker_id]]) follows [[audio]] without copying the original audio signal. Voice characteristics: [[voice_description]]
```

Use `[[audio]]` with two opening brackets. Literal labels such as “Voice characteristics:” remain even when their placeholder is empty; keep the separate optional `voice_characteristics` template if you want the entire clause omitted for missing descriptions. Preview the result with the relevant reference before generating.

## Reference preview

Expand **Preview with a reference** in the template node. Search by name or paste a tag such as `{Character_BC}` or `{Character_rm}`, then choose a saved reference, built-in character, or RefMod. Each template field shows its rendered example underneath; **Complete example prompt** shows the full compiled result. Edits update the preview automatically. Audio/video usage selectors let you inspect different wording modes.

The preview uses the actual deterministic compiler without loading models or encoding media. Its single-reference numbering is illustrative, not the numbering in your workflow. Phrases that do not apply are labeled accordingly; a single-reference example does not invoke multi-speaker global bindings. References without attached voices do not receive invented audio slots. The chosen preview reference is saved with the node but is not included in its template STRING output. Restart ComfyUI and refresh the browser after installing this preview feature.

## Available fields

The tables below show the placeholders used by each **default wording**, not an allowlist. All fields also accept the shared vocabulary above and placeholders shown in other rows, subject to the available context.

### Subject/media definitions

| Field | Placeholders |
|---|---|
| `subject_definition` | `[[subject]]`, `[[description]]` |
| `subject_media` | `[[media]]` |
| `subject_description` | `[[description]]` |
| `picture_description` | `[[picture]]`, `[[description]]` |
| `video_reference` | `[[video]]`, `[[description]]` |
| `video_motion_reference` | `[[video]]`, `[[description]]` |
| `video_continuation` | `[[video]]`, `[[description]]` |
| `video_editing` | `[[video]]`, `[[description]]` |
| `soundtrack_reference` | `[[audio]]`, `[[video]]` |
| `soundtrack_reuse` | `[[audio]]`, `[[video]]` |
| `media_audio_reference` | `[[audio]]`, `[[role]]`, `[[description]]` |
| `media_audio_reuse` | `[[audio]]`, `[[role]]`, `[[description]]` |

### Voice definitions and dialogue bindings

| Field | Placeholders |
|---|---|
| `voice_reference` | `[[audio]]`, `[[subject]]`, `[[speaker]]` |
| `voice_reuse` | `[[audio]]`, `[[subject]]`, `[[speaker]]` |
| `voice_exclusive_reference` | `[[audio]]`, `[[subject]]`, `[[speaker]]`, `[[name]]` |
| `voice_exclusive_reuse` | `[[audio]]`, `[[subject]]`, `[[speaker]]` |
| `voice_characteristics` | `[[voice_description]]` |
| `dialogue_binding_reference` | `[[audio]]` |
| `dialogue_binding_reuse` | `[[audio]]` |
| `voice_cue_reference` | `[[audio]]` |
| `voice_cue_reuse` | `[[audio]]` |
| `voice_cue_introduction` | `[[phrase]]` |
| `text_voice_introduction` | `[[description]]` |
| `global_binding` | `[[bindings]]` |

### Summary additions

| Field | Placeholders |
|---|---|
| `summary_editing` | `[[sources]]` |
| `summary_voice_reference` | `[[audio]]`, `[[identity]]` |
| `summary_voice_reuse` | `[[audio]]`, `[[identity]]` |
| `summary_task_prefix` | `[[task_prefix]]` |

### Retention analysis

| Field | Placeholders |
|---|---|
| `retention_appearances` | `[[shots]]` |
| `retention_subject` | `[[subject]]`, `[[appearances]]` |
| `retention_voice_reference` | `[[audio]]`, `[[identity]]` |
| `retention_voice_reuse` | `[[audio]]`, `[[identity]]` |

