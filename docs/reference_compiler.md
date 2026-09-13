# Deterministic H3 reference compiler

In **H3 Tagged Reference Prompt**, select `compiler_mode = deterministic`.
Existing workflows default to `legacy`; their free-form replacement behavior and output sockets stay compatible.
Restart ComfyUI and refresh the browser to expose the new options.

## Validate a complete prompt list before a loop

Add **SKEBA H3 Prompt List Validator** before the prompt splitter:

1. Connect the complete prompt-list string to the validator's `text` input.
2. Connect its `text` output to **Skeba Batch Text (Prompt Loop)**. This dependency
   prevents the loop from receiving any prompt until the whole list has passed.
3. Connect `compiler_mode` to the corresponding input on **H3 Tagged Reference Prompt**,
   directly or through your Setter/Getter pair. Convert the compiler_mode widget to an
   input if needed. The output uses the same combo type as the reference node.
4. Optionally connect `report` to a text display. `validation_enabled` also has a Boolean
   output for other workflow controls.

With validation on, each prompt is compiled independently against the current library;
the node reports all failing prompt numbers together and stops before releasing the list.
With validation off, it passes the original text untouched and outputs `legacy` mode.
With validation on and successful, it outputs `deterministic` mode. Use the toggle widget,
not ComfyUI's generic node bypass, to switch the mode output correctly.

Set the same delimiter and skip_empty behavior on validator and splitter (defaults are
`|` and true). Match the video usage, audio usage, and voice isolation settings to the
reference compiler. Validation passes the original semantic text through, not the compiled
numbered output. Each prompt must redeclare its own temporary resources.

Library revisions invalidate cached validation. The validator checks structural syntax,
reference lookup, declarations, and allocation limits. It does not enforce voice placement,
speech verbs, or character/voice matching, and does not decode media or guarantee render quality.

Use these five headings, on their own lines, in this order:
`subject_definitions`, `summary`, `detailed_description`, `overall_soundscape`,
`non_diegetic_music`. Each heading ends with a colon. Existing six-section prompts can
still include `retention_analysis` between summary and detailed_description. If omitted,
it stays absent from the output. Authored retention entries are preserved and sorted;
no retention entries or missing/invalid-marker warnings are generated.

The preferred language-header voice syntax and omission of retention are local SKEBA
choices based on render testing, rather than requirements of the official six-section guide.

## Authoring

- `{saved_tag}` resolves a library entity. Set its library reference type first.
- `§saved_tag§` resolves that character's attached audio or voice description.
- `§video_tag§` explicitly selects an enabled synchronized soundtrack from a saved
  video. `{video_tag}` still selects the visual/whole-video reference. An available
  soundtrack alone does not add an audio definition or audio task.
- Declare temporary resources before the sections: `<character:cashier = A cashier in a red uniform.>`.
  Use `<character:cashier>` inside sections. Supported temporary types are character, voice, location, object.
- A temporary voice and character share the same name; saved and temporary names remain separate.
- Put each used character/location/object tag once in `subject_definitions`.
- Preferred speech: `{saved_tag} says, <d>[English §saved_tag§]Hello.</d>`
  or `<character:cashier> replies, <d>[English <voice:cashier>]Hello.</d>`.
  In dialogue, an actual voice reference becomes a compact `<Audio N>` label;
  a text-only voice becomes its literal description. Spoken words after `]` are unchanged.
- Older before-dialogue voice tags and inline descriptions remain supported. Voice tags
  can appear in other prose without a required speech verb or matching-character check.
  Unknown references and unavailable video soundtracks still produce resource errors.
- Speakers are inferred from dialogue events and explicit voice cues. Ambiguous prose is
  accepted rather than rejected; use a clear character tag and voice header for predictable
  speaker numbering. References in other sections activate audio without inventing speech.
- Author semantic tags, not numbered runtime labels. Unbalanced dialogue tags and malformed
  section structure still fail validation. Keep dialogue in detailed_description as an
  authoring convention; its placement is no longer a parser restriction.

See [the complete temporary-resource example](../example/reference_compiler_prompt.txt).
For saved references, definitions include the saved name, literal description, and media provenance.
Other sections use the assigned Subject number. Voice descriptions are inserted literally without paraphrasing.

Definitions are sorted by assigned Subject number, with each voice relationship beside
its owning subject. A summary made entirely of separate subject-led lines (one subject
per line, optionally bulleted) is also sorted numerically. Narrative paragraphs, wrapped
prose, and lines mentioning multiple subjects retain their authored order. Sorting does
not change media slots, speaker assignment, or detailed-description event order.
The summary is emitted as one paragraph with its task header on the same line.
Editing summaries open with the required sentence identifying the source video.
An explicit actual voice-audio tag in summary now becomes its Audio label; a text-only
voice becomes its literal description. Prefer omitting text-only voice tags there.

Used music, whole-video sources, and synchronized soundtracks receive role definitions
automatically. Source-only image provenance does not create a separate Picture entry.
Lyrics quoted as cues from reused music/soundtracks do not allocate an extra Speaker ID.

## Numbering and media

The compiler discovers resources and explicit vocal events before assigning numbers.
Speaking characters come first, in first-speech order in detailed_description. Each
speaking character has the same Subject and Speaker number: Subject 1 / S1, Subject 2 / S2.
Write events in playback order. Silent subjects follow, retaining image-plus-audio,
image, audio, then description-only priority, with library/declaration order for ties.

Actual image and standalone audio outputs follow the same speaker-first order, so a cast
with both media for every speaker aligns Subject, Speaker, Picture, and Audio numbers.
Only real media allocates slots: missing images or text-only voices can offset media
numbers. Enabled video soundtracks precede standalone audio, matching H3's
encoder. The same allocation drives the node's direct outputs and deferred reference bundle.
Numbers are local to each prompt and can change when a different character speaks first.
The legacy replacement mode is unchanged.
Limits remain 9 images, 3 standalone audio files, and 3 videos; exceeding them raises an error.

Silent characters retain their visual references but their attached standalone voice clips
are not allocated, loaded, or counted toward the audio limit. Voice use is determined before
numbering and limit checks. A voice tag only in subject_definitions does not activate audio;
an explicit voice tag in speech, summary, retention, or soundscape does. Omit those voice
tags for silent characters. Text-only voices do not allocate Audio slots. Music uses Audio;
video uses Video and does not automatically become a Subject.

`auto_crop_voice_references` defaults to true in both compiler modes. Each distinct
selected character voice reference keeps its first `15 / voice_count` seconds:
15 seconds for one voice, 7.5 each for two, or 5 each for three. Shorter sources
stay unchanged; unused time is not redistributed. Disable the toggle for uncropped
comparisons. Original library files, sample rates, channels, and reference ownership
are preserved. Explicitly reused audio, music, and synchronized video soundtracks are
excluded, so mixed audio can still exceed the overall 15-second allowance.

The same crop applies to direct outputs and deferred reference bundles. The mapping
reports the per-voice cap; cached nodes report it even on cache hits. Audio cache keys
include the cap, so a changed voice count or toggle cannot retrieve an incompatible
latent. Bundles without crop metadata retain their prior uncropped behavior.

`compiler_video_usage` selects reference, motion_reference, continuation, or editing.
Reference and motion_reference produce reference generation, not video continuation.
`compiler_audio_usage` selects reference or reuse for audio actually used in the prompt.
Audio guidance adds reference generation plus audio reference; copying adds audio reuse.
Voice definitions and speech templates distinguish copied signal from timbre reference.
`compiler_voice_isolation` defaults to true. Character audio definitions explicitly
restrict the reference to its owner. At each speaking turn, the compiler states the
owner's exclusive audio assignment and excludes other active characters' voice clips.
This uses actual Subject/Speaker/Audio mappings, not matching numbers. Music, video
soundtracks, unused audio, and text-only voices do not become competing voice clips.
Disable the option to compare renders without these extra prompt instructions.
The summary task header is computed from usage. These options apply to referenced assets
throughout this prompt. Keyframe completion is not inferred from an image.

The existing `mapping` STRING output contains JSON with resource identities, physical slots,
subject/speaker numbers, actual audio usage, task types, and warnings.
`generated_voice_retention` remains an empty list for mapping compatibility. Retention
analysis is optional and no longer contributes validation warnings. The optional
`compiler_voice_isolation` setting still adds prompt guidance; it does not enforce a
speech grammar or reject cross-character voice references. Disable it for a compact
header-format experiment without extra ownership/exclusion prose.

Errors still identify unknown resources, malformed declarations, missing required
sections/definitions, unresolved authoring tags, unbalanced dialogue, and invalid slots.
Generated-video quality still needs a render check.

For detailed writing rules and complete examples, use [the authoring skill](Skeba_Minimax_Skill.md).
Concrete frame anchors, multi-source subjects, multiple subjects extracted from one
asset, and independent nonvisual narrators need explicit representations that are not
yet supported by this authoring syntax. Do not substitute guessed runtime labels.
