# Deterministic H3 reference compiler

In **H3 Tagged Reference Prompt**, select `compiler_mode = deterministic`.
Existing workflows default to `legacy`; their free-form replacement behavior and output sockets stay compatible.
Restart ComfyUI and refresh the browser to expose the new options.

Use these six section headings, on their own lines, in this order:
`subject_definitions`, `summary`, `retention_analysis`, `detailed_description`,
`overall_soundscape`, `non_diegetic_music`. Each heading ends with a colon.
The compiler replaces semantic tags; it does not write the scene, dialogue, timing,
or music description for you. It can fill a missing, mechanically known character
voice-timbre retention entry; other retention instructions remain authored.

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
- For speech, use `{saved_tag} says §saved_tag§, <d>[English]Hello.</d>`
  or `<character:cashier> says <voice:cashier>, <d>[English]Hello.</d>`.
  Also supported: asks, replies, whispers, shouts, sings, speaks, exclaims.
  Add `(off-screen)` immediately after the entity tag for an off-screen turn;
  its Speaker ID is reused when that character appears on-screen.
- Keep reference tags outside dialogue. Author semantic tags, not numbered runtime tags, in this mode.

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
Complete dialogue and lyrics are accepted only in detailed_description. Lyrics quoted
as cues from reused music/soundtracks do not allocate an extra Speaker ID.

## Numbering and media

The compiler discovers resources across all sections before assigning numbers.
Subjects prioritize image plus audio, image, audio, then description-only resources.
Ties follow library order, then temporary declaration order. Speakers follow their first
explicit vocal event in detailed_description, independently of Subject numbers.
Write those events in playback order.

Picture, Audio, Video, Subject, and Speaker counters are independent. Only real media
allocates media slots. Enabled video soundtracks precede standalone audio, matching H3's
encoder. The same allocation drives the node's direct outputs and deferred reference bundle.
Limits remain 9 images, 3 standalone audio files, and 3 videos; exceeding them raises an error.

A silent character can have an allocated audio file without adding an Audio reference or
audio task to the prompt. Text-only voices do not allocate Audio slots. Music uses Audio;
video uses Video and does not automatically become a Subject.

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
Missing character voice-timbre entries are generated as `reference`, with Subject/Audio
ownership and no Speaker IDs. Authored entries are preserved, including custom weak
reference choices. Reused signal, music, video, and visual retention still require authored
analysis; the compiler does not guess full versus partial copying or shot timing.
`generated_voice_retention` lists the automatically added Audio slots in mapping JSON.
Retention warnings identify remaining missing entries, duplicates, and markers from the
wrong category. Speaker IDs are confined to vocal events and their audio definitions.
Errors identify missing resources, malformed declarations, unsupported vocal patterns,
missing sections/definitions, unresolved tags, and invalid slot use before media loading.

The compiler follows the section and reference-label conventions in the
[official H3 reference prompt guide](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md).
It validates and compiles authoring syntax; generated-video quality still needs an H3 render check.

For detailed writing rules and complete examples, use [the authoring skill](Skeba_Minimax_Skill.md).
Concrete frame anchors, multi-source subjects, multiple subjects extracted from one
asset, and independent nonvisual narrators need explicit representations that are not
yet supported by this authoring syntax. Do not substitute guessed runtime labels.
