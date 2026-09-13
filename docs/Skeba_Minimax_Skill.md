---
name: skeba-minimax-prompts
description: Write and revise MiniMax H3 video prompt sequences for SKEBA's deterministic H3 Tagged Reference Prompt compiler, using saved and temporary semantic references with explicit dialogue and clip continuity.
metadata:
  updated: 9/11/2026 5:30 PM
---

# SKEBA MiniMax H3 prompt writing

Write authoring prompts for **H3 Tagged Reference Prompt** with **compiler_mode = deterministic**. This mode must be selected on the node; restarting ComfyUI does not change a saved legacy setting. Legacy mode leaves temporary tags unchanged.

The prompt writer owns the story, scene descriptions, dialogue, timing, and continuity. The compiler owns reference discovery, definitions, runtime numbering, and summary task headers. Preserve the user's creative intent and spoken words.

Use the five-section SKEBA format below. Do not generate `retention_analysis`. Put appearance and continuity requirements directly in the relevant scene descriptions. This is a deliberate local variation from the official six-section guide, based on the user's render tests. Voice references go inside the dialogue's language brackets: `<d>[English §saved_tag§]Spoken words.</d>`. Do not describe that placement as an official MiniMax requirement.

Write section prose in English, preserving the original language of dialogue, lyrics, and visible scene text. Do not paste already-numbered official examples into deterministic compiler input.

For implementation details or debugging, read [reference_compiler.md](reference_compiler.md). The local `../reference_compiler.py` is the authority for currently accepted syntax. This skill targets that implementation, not arbitrary raw H3 prompts.

## Author semantic references throughout

Never author numbered Subject, Speaker, Picture, Audio, or Video labels in compiler input. This includes `(S1)` and numbered labels inside declarations or dialogue. The compiler rejects authored runtime labels. Do not precompile the prompt yourself.

Use these separate namespaces:

| Meaning | Authoring syntax | Requirement |
| --- | --- | --- |
| Saved entity or media resource | `{saved_tag}` | Exact existing library tag |
| Saved character's voice | §saved_tag§ | Same saved character; attached audio or voice description |
| Saved video's synchronized soundtrack | §video_tag§ | Existing video with an enabled audio track; no automatic speaker |
| Temporary character | `<character:cashier>` | Earlier character declaration |
| Temporary voice | `<voice:cashier>` | Earlier voice declaration and matching temporary character |
| Temporary location | `<location:coffee_shop>` | Earlier location declaration |
| Temporary object | `<object:cup>` | Earlier object declaration |

Preserve saved tag spelling exactly, including spaces and `_BC` suffixes. Do not invent a saved tag or assume a built-in character has an attached image/audio file. Confirm available resources from the supplied catalog or library when accessible. Missing saved identities needed by the user require clarification; incidental new characters can use temporary declarations.

Repeat semantic entity tags in summary and action descriptions when referring to those entities. Repeated tags reuse one identity; they do not load another copy of the asset. The old rule to invoke a tag only once and then manually use Subject numbers no longer applies.

Use ordinary human-readable names when those names are spoken aloud. Do not emit caret/tilde legacy tags, backslash-escaped syntax, or HTML entities in place of literal `<`, `>`, `{`, `}`, or section signs.
## Voice tag placement

Put the semantic voice reference inside the opening language brackets, after the language name:

```text
{George Costanza_BC} says, <d>[English §George Costanza_BC§]They did? Because I can be more intimidating.</d>
<character:cashier> replies, <d>[English <voice:cashier>]Your order is ready.</d>
```

With attached audio the compiler emits a compact label such as `[English <Audio 1>]`. Without attached audio it substitutes the available voice description. The text after `]` is the spoken content; preserve all its words and punctuation. Repeat the voice reference inside the language brackets for each new dialogue block, including repeated turns by the same speaker.

The compiler accepts older before-dialogue voice tags and flexible prose without enforcing a speech-verb list, matching character/voice pairs, or voice placement. That tolerance is for experimentation, not permission to accidentally assign another person's voice. Normally keep the character and voice tags associated with the intended performer; honor deliberate voice imitation when the user requests it. Do not move a header voice tag outside the brackets to satisfy the old rules.

Do not add voice tags for silent characters. Additional explicit voice references elsewhere can activate audio inputs even without spoken dialogue. Prefer ordinary prose when merely describing silence, ambience, or voice behavior.

## Temporary declarations

Put declarations before `subject_definitions`, one per line:

```text
<character:cashier = A cashier in a red uniform.>
<voice:cashier = A young male voice with a friendly tone.>
<location:coffee_shop = A cozy coffee shop with wooden tables.>
<object:cup = A white ceramic coffee cup.>
```

After this prefix, reference resources without `= description`. Names must start with an ASCII letter and contain only ASCII letters, digits, or underscores. Types are exactly `character`, `voice`, `location`, and `object`, in lowercase. Descriptions must be nonempty literal prose without nested reference tags or angle brackets.

Declare each type/name pair once per prompt. Use matching temporary voice and character names for ordinary speech. Explicitly requested alternate voice references are permitted. Saved `{cashier}` and temporary `<character:cashier>` are different resources, even when their names match. Avoid reusing a temporary name across unrelated types.

Temporary resources are description-only. They do not create media inputs. Use declarations only for resources active in this clip.

## Every prompt is self-contained

Each prompt is compiled separately with a fresh temporary registry. Nothing declared or defined in Prompt 1 is available to Prompt 2. This applies to every clip, including direct same-location continuations without `[new_location]`. Inherited video frames carry visual state; they do not carry prompt declarations, definitions, or reference numbering.

EVERY temporary reference used in a prompt must be fully redeclared inside that prompt.

This applies to all temporary types:

- `<character:name>`

- `<voice:name>`

- `<location:name>`

- `<object:name>`

A temporary reference declaration from an earlier prompt NEVER carries forward at the compiler level.

For example, if several prompts take place in the same bar, every prompt that uses `<location:bar>` must repeat the complete declaration:

<location:bar = A dim neighborhood bar with a long wooden counter, red vinyl stools, mirrored liquor shelves, warm amber pendant lights, and dark wood-paneled walls.>

The later prompt must NOT use only:

<location:bar>

unless the full `= description` declaration has already appeared earlier in that SAME prompt.

Likewise, an object such as `<object:cup>` must be fully redeclared in every prompt where it appears.

For every individual prompt:

- Repeat the full `= description` declaration for every temporary character, voice, location, or object referenced anywhere in that prompt.

- Never rely on a temporary declaration from another prompt, even when the resource represents the same continuing physical person, place, or object.

- Include each used character, location, and object tag once in that prompt's subject_definitions, including saved library entities. A previous prompt's definition does not count.

- Saved library entries remain available by their exact saved tags; do not recreate them as temporary declarations. Invoke them again in the current prompt so its compiler can discover their media and generate local definitions.

- Repeat the matching voice tag at every speaking event. If it is a temporary voice, repeat both its voice declaration and its matching character declaration in this prompt.

- Carry forward the full concrete description of a continuing temporary resource. Do not substitute “same as before,” “previously defined,” or a bare tag for its declaration. Keep identity details consistent and change state details only when the story requires it.

IMPORTANT: redeclaring a temporary location does NOT mean the story has entered a new physical location. Declaration scope and physical-location continuity are separate concepts. `[new_location]` is determined by story geography, not by whether the temporary location had to be redeclared for compilation.al appearance constraints, rather than shortening it to this example.

## Five required sections

Each prompt contains these headings exactly once, in this order, with the colon and heading on their own line. Do not add titles, commentary, numbered prefixes, or additional section headings inside the prompt.

### subject_definitions

Place every active character, location, and object entity tag on a separate line, exactly once. The compiler turns each tag into its complete definition. Do not wrap a tag in a manually authored definition such as `is {tag}` or append another copy of the library description.

The compiler sorts these definitions by the assigned Subject number and places used voice relationships beside their owning subjects. Keep authoring semantic tags; do not predict or manually arrange runtime numbers.

Used whole-video and music references receive separate role definitions automatically, even when first invoked later. They may also be listed once as their saved tag in subject_definitions. Their physical slots do not become Subjects. An image used only as an entity's provenance does not need a separate Picture definition.

Temporary voices do not need their own definition line. Do not write `S1 VOICE:` blocks or manually bind speaker numbers. Explicit speech events supply the binding, and the compiler adds used saved-audio relationships automatically. Put shot-specific clothing, posture, placement, and continuity requirements in detailed_description.

### summary

Write one short English paragraph describing the target video and its main reference relationships, using semantic entity tags. Keep voice tags in the dialogue's language brackets and omit full dialogue from the summary. Leave out bracketed task headers; the compiler computes them from actual media usage.

When a summary should be sorted by subject, write separate self-contained lines, each starting with an entity tag and mentioning only that entity. The compiler sorts this format by assigned Subject number, then joins the lines into one paragraph. The task header and paragraph share one line. For video editing, the compiler supplies the required opening identifying the edited source video. Ordinary narrative sentences involving multiple subjects keep their authored order; do not split an interaction merely to force sorting.

### Timing: allow natural dialogue to finish

Encourage explicit shot timestamps, especially when dialogue or a change of speaker is involved. Use `[Shot N] At MM:SS.mmm, ...`, including `At 00:00.000` for the opening shot when timing the sequence. The user's latest tests favor well-paced timing: cuts scheduled too quickly may cause the next character to pick up another character's unfinished dialogue. Treat this as a local authoring preference, not a guarantee about model behavior.

Set the next shot's start from the current line's natural speaking length, not from evenly divided shot intervals. Read the line at its intended delivery pace and allow for punctuation, pauses, emphasis, and any action before speech starts. Leave a brief natural beat after the line ends so the speaker can close their mouth before the cut. Slow, emotional, or hesitant delivery needs more time; do not force fast delivery just to meet a timestamp.

For example, a silent arrival at 00:00.000 followed by a speaker at 00:01.500 and the next speaker at 00:05.000 gives the first speaking shot 3.5 seconds. That spacing worked in the user's test; it is not a fixed allowance for every line. Longer dialogue needs a later cut. Give the final speaker enough time before the clip ends as well.

Pair timing with clear handoffs: "[Character] alone delivers the complete line. [Character] finishes speaking and closes their mouth before the next shot begins." Keep shots and speaking turns in playback order. Respect the requested overall clip length; if the dialogue cannot fit naturally, use fewer turns or split across clips when permitted, rather than crowding the timestamps or silently changing the spoken words. Untimed shots remain acceptable when precise timing adds no value or the user requests natural untimed pacing.

### detailed_description

Begin with one or two English sentences establishing presentation/style before `[Shot 1]`. Use sequential `[Shot N]` labels and encourage timestamps, especially for dialogue; follow the natural speaking-length guidance above before placing each cut. For each shot establish composition, visible appearance and positions, environment and lighting, actions/state changes, camera movement (type, amplitude, speed when relevant), current sound, and where references take effect. At an important entity's first visible appearance, describe the referenced characteristics actually visible in that shot. Do not reduce this section to plot or reference mappings.

For generation prompts, normally aim for 350-500 English words here. Dialogue-heavy scenes prioritize a feasible complete spoken timeline over reaching that range. Editing detail scales with the changes. One shot alone is not a reason to omit necessary detail; do not invent additional action to pad a word count. Write events in playback order, because the compiler assigns speakers in source order rather than sorting timestamps.

Use semantic tags for entities in actions and speech. Additional staging belongs before or after the speech pattern, not inserted inside its required structure.

### overall_soundscape

Describe diegetic sound: room tone, footsteps, clothing, cups, doors, impacts, weather. Do not repeat full dialogue. For alternating speech, describe one active voice at a time using ordinary prose; do not author S-number labels or place voice tags here merely because a character owns audio.

### non_diegetic_music

Describe audience-only music with instrumentation, tempo, and dynamic development, or write `N/A`. A supplied music resource uses its saved `{music_tag}` and must have a real audio file. Do not use character voice tags or a visual `{video_tag}` as music resources. If a synchronized video soundtrack actually supplies the score layer, cite `§video_tag§` and state whether that layer is copied or referenced. Describe ambience/effects layers in overall_soundscape and audience-only score in non_diegetic_music, even when they share one source.

## Dialogue and voice guidance

Use the language-header placement above for saved and temporary voices. A character without a voice reference can still speak with an inline description, for example `<character:guest> says in a cheerful voice, <d>[English]Hello.</d>`. No audio file is invented. Natural delivery verbs and action clauses are accepted; `says` is a useful convention rather than a compiler requirement.

Keep each complete spoken turn with its intended performer. The compiler discovers speakers in first-vocal-event order and gives them matching Subject/Speaker numbers. Write events in playback order. A voice tag in a language header can identify a speaker even when surrounding prose is unconventional. Music and video soundtrack cues do not automatically become character speakers.

`compiler_voice_isolation` is an optional prompt augmentation, not a validation gate. Set it to false when testing the compact header format without additional generated voice-exclusion prose. The new voice syntax does not require that option. Do not author numbered ownership or exclusion rules yourself.

Use `<scenetrans>` and `<cutoff>` only for intentionally continuous dialogue across a cut or intentionally truncated speech. For ordinary turn-taking, finish the line before the next shot. Keep each entire dialogue block on the same speaking face when practical.

### One speaking character per shot

A single `[Shot N]` may contain intelligible dialogue from AT MOST ONE character.

This is a hard authoring rule.

If two different characters speak, their dialogue MUST occur in separate shots, even when the exchange is very short.

INVALID:

[Shot 2] {Jerry} says, <d>[English §Jerry§]What happened?</d> {George} replies, <d>[English §George§]I don't know.</d>

VALID:

[Shot 2] At 00:01.500, frame {Jerry}. {George} remains silent. {Jerry} says, <d>[English §Jerry§]What happened?</d> Jerry finishes and closes his mouth.

[Shot 3] At 00:04.000, cut to {George}. {Jerry} remains silent. {George} replies, <d>[English §George§]I don't know.</d> George finishes and closes his mouth.

A character may have multiple dialogue clauses within one shot only when every clause belongs to that SAME character. Introducing dialogue from another character requires a new `[Shot N]`.

Listeners may remain visible in the speaking character's shot, but they must remain silent and should keep their mouths closed. When useful for voice isolation, frame only the active speaker.

Shot boundaries therefore also act as dialogue-speaker boundaries:

ONE SHOT = ZERO OR ONE SPEAKING CHARACTER.

For this SKEBA authoring convention, put each speaking character in a separate shot unless the user explicitly requests another structure. This is a staging choice, not a compiler validation rule.

### Character isolation within shots

When a shot is explicitly framed around only one character, do NOT mention any other character anywhere inside that `[Shot N]`.

This is a hard authoring rule.

If a shot says or implies:

- "shows only {character}"

- "frame only {character}"

- "a close-up of {character}"

- "a solo shot of {character}"

- "isolates {character}"

- or otherwise establishes that only one character is present in the shot

then all subsequent prose inside that shot must refer only to that visible character, relevant objects, the environment, camera behavior, and sound.

Do NOT mention another character merely to establish that they are:

- off-camera

- off-screen

- silent

- listening

- unseen

- outside the frame

- waiting nearby

- being looked toward

- being spoken toward

The absence of another character should be expressed by omission, not by naming that character.

INVALID:

[Shot 1] A close medium shot shows only {George Costanza_BC} at the dining area holding <object:odd_snack_bag>. Jerry is off-camera and silent. George removes one small dried piece and confidently holds it toward the unseen Jerry. {George Costanza_BC} says, <d>[English §George Costanza_BC§]They came from a guy who said they improve your perspective.</d>

VALID:

[Shot 1] A close medium shot shows only {George Costanza_BC} at the dining area holding <object:odd_snack_bag>. George removes one small dried piece and confidently holds it outward toward the edge of the frame. {George Costanza_BC} says, <d>[English §George Costanza_BC§]They came from a guy who said they improve your perspective.</d> George finishes speaking and closes his mouth. The camera performs an unnecessarily slow two-second zoom toward the snack.

When interaction direction is necessary, describe it without identifying the absent character.

Prefer:

- "looks toward the edge of the frame"

- "holds it toward someone outside the frame"

- "gestures toward the empty side of the composition"

- "looks just past the camera"

- "directs the remark outside the frame"

Avoid:

- "looks toward Jerry off-camera"

- "holds it toward the unseen Jerry"

- "Elaine remains off-screen"

- "Kramer listens outside the frame"

This rule applies only within the individual shot. Other characters may still be defined in subject_definitions, summary, other shots, and other required sections when they are active in the overall prompt.

SHOT CHARACTER ISOLATION RULE:

SOLO CHARACTER SHOT → DO NOT NAME ANY OTHER CHARACTER INSIDE THAT SHOT.

### Solo-shot environmental grounding

A solo character shot means that only one CHARACTER is referenced in that shot. It does NOT mean the character should be visually isolated from the established environment.

When framing a saved reference character alone, especially when the source image is a character sheet, portrait, studio photograph, or plain-background reference, explicitly place the character inside the current physical location before specifying the camera framing.

Prefer:

"shows {character} in the room in a crooked medium close-up"

"shows {character} standing inside {location} in a medium shot"

"shows {character} near the kitchen counter in a close medium shot"

"finds {character} seated on the sofa inside {location}"

Avoid using visual-isolation language such as:

"isolates {character}"

"an isolated shot of {character}"

"separates {character} from the background"

unless actual environmental isolation is intentionally desired.

IMPORTANT:

SOLO CHARACTER SHOT ≠ VISUALLY ISOLATED CHARACTER.

The character should remain naturally embedded in the established physical environment, with the location providing the visible background, lighting, perspective, and spatial context.

For saved reference characters, use this preferred construction:

CHARACTER + PLACEMENT IN CURRENT LOCATION + CAMERA FRAMING

Example:

[Shot 3] An abrupt amateurish cut shows {Mr_Roarke} in the room in a crooked medium close-up.

This keeps the shot restricted to {Mr_Roarke} without encouraging the generator to reproduce the isolated composition or plain background of the character reference image.

Do not mention another character merely to establish the current character's spatial relationship. Ground the character relative to the room, furniture, architecture, or other environmental features instead.

A character does not need to be explicitly described as silent or off-camera to prevent them from speaking. Their absence from the shot prose is preferred because it reduces unintended character, identity, and voice mixing.

## Media and task ownership

The compiler discovers resources and vocal events before allocating slots. Speaking characters come first in first-speech order and receive matching Subject and Speaker numbers. Their actual image and voice outputs follow the same order. Silent subjects follow using existing media priority and library/declaration order. Missing media and synchronized video soundtracks can offset Picture or Audio numbers. All numbers are local to the current prompt; never guess them from an earlier clip.

Only actual media allocates physical slots. A text-only voice creates no Audio slot. Unused attached character voices are not loaded in deterministic mode. Do not add voice tags for silent characters merely because they have an audio attachment.

`auto_crop_voice_references` defaults to true. Used character voice clips share a 15-second budget: 15 seconds for one, 7.5 each for two, 5 each for three. Keep shorter clips unchanged without padding or redistribution. Cropping applies to direct and deferred loading and never edits library files. Music, explicitly reused audio, and video soundtracks remain outside this voice-only budget. Disable the toggle for an uncropped comparison.

Music becomes an Audio reference, `{video_tag}` becomes a Video reference, and `§video_tag§` explicitly selects that video's enabled soundtrack; neither automatically becomes a Subject or speaker. A video's available soundtrack does not create an audio task/definition until explicitly used. A soundtrack-only tag does not imply editing or continuation of the visual track. Some Audio slots represent music or video soundtracks, so the old rule that every Audio slot belongs to a speaking character is incorrect. Enabled video soundtracks are numbered before standalone audio. Use the node's JSON `mapping` output to inspect actual ownership; never infer ownership from matching numbers.

Set task purpose using node options when the task calls for it:

- `compiler_video_usage = reference` or `motion_reference`: video supplies reference material; neither implies continuation.
- `compiler_video_usage = continuation` or `editing`: explicitly requests that video task.
- `compiler_audio_usage = reference` or `reuse`: describes how intentionally used audio is used.

These options apply across the prompt unless resource metadata overrides them. Same-location continuity through the workflow does not by itself mean a saved video is a continuation input. Do not write a task header to override node options. Audio used as generation guidance adds reference generation plus audio reference; directly reused audio adds audio reuse. Voice-reuse wording explicitly describes signal reuse rather than timbre-only guidance. Keyframe completion is not inferred by this compiler. A text-only prompt may have no task header; that is valid.

Current physical limits are 9 images, 3 standalone audio files, and 3 videos, counting only allocated media. Do not drop requested references merely to fit: identify the limit and adapt the resource selection with the user when needed.

## Full-reference features outside the current authoring model

The official guide supports more reference relationships than this compiler currently models. Do not fake support by inserting runtime numbers or inventing new temporary types:

- Concrete first/key/last-frame anchors and standalone storyboard Picture roles need explicit asset-role inputs; ordinary entity images are provenance today.
- Several source assets defining one Subject, or several Subjects extracted from one source, need an explicit identity/source mapping. Separate saved tags currently remain separate resources.
- Independent narrators without a visible Subject and group speech need a dedicated vocal-source model. Do not create a visible character merely to obtain a speaker number.
- Per-shot reuse/reference changes for the same audio, or mixed purposes for several video assets, need role metadata beyond the global node options. Do not infer these from prose.

For those requests, identify the missing representation and adapt the workflow explicitly. Keep compiled runtime output separate from deterministic authoring input.

## Clip boundaries and continuity

For SKEBA sequence authoring, keep one physical location per clip. Use multiple angles and movement within that environment. Start a new clip for a different physical location unless the user explicitly requests another structure.

`[new_location]` means that the sequence is entering a DIFFERENT physical place from the immediately preceding clip. It does NOT mean that a location declaration is new to the current prompt.

Use `[new_location]` as the first line when:

- the sequence begins with its first physical location; or
- the current clip takes place in a physically different location from the immediately preceding clip.

Do NOT use `[new_location]` when returning to or continuing in a location that has already been established as the current physical place.

Most importantly, when consecutive prompts use the same location identity, they are the SAME physical place even though the temporary location declaration must be repeated because each prompt compiles independently.

Example:

Prompt 1:
[new_location]
<location:bar = A dim neighborhood bar with a long wooden counter...>

Prompt 2:
<location:bar = A dim neighborhood bar with a long wooden counter...>

Prompt 2 MUST repeat the full declaration, but MUST NOT use `[new_location]`, because `<location:bar>` still represents the same established physical bar.

Therefore:

TEMPORARY DECLARATION SCOPE:
Every prompt starts fresh and must redeclare `<location:bar = ...>`.

STORY LOCATION IDENTITY:
Repeated use of `<location:bar>` represents the same physical location unless the story explicitly establishes otherwise.

These concepts must never be confused.

Do not use `[new_location]` for:

- a repeated location declaration;
- a same-location continuation;
- a new camera angle;
- a close-up or reverse angle;
- movement to another part of the same room or continuous physical environment;
- a character entering or leaving;
- a same-location time jump;
- a change in lighting, staging, furniture state, or character positions.

If Prompt 1 uses `<location:bar>` and Prompt 2 also uses `<location:bar>`, Prompt 2 does not receive `[new_location]`.

If Prompt 3 changes to `<location:street>`, Prompt 3 begins with `[new_location]`.

If Prompt 4 continues at `<location:street>`, Prompt 4 does not begin with `[new_location]`.

`[new_location]` is a workflow control marker based on physical scene transitions. It is not a declaration marker, section heading, or video-task header.
## Complete example: temporary resources only

This example can compile without any saved library entries. It intentionally creates no physical media slots.

```text
[new_location]
<character:cashier = A cashier in a red uniform.>
<voice:cashier = A young male voice with a friendly tone.>
<location:coffee_shop = A cozy coffee shop with wooden tables.>

subject_definitions:
<character:cashier>
<location:coffee_shop>

summary:
<character:cashier> announces a ready order in <location:coffee_shop>.

detailed_description:
The target video uses a realistic, quietly observed cafe style with warm indoor light.
[Shot 1] At 00:00.000, a medium shot inside <location:coffee_shop> shows <character:cashier> standing behind the counter under soft indoor light. Only the cashier is visible. The camera is at counter height, with the cashier just RIGHT of center and the empty waiting area on the LEFT. The red uniform is clearly visible from the chest upward; the cashier keeps his shoulders relaxed and both hands resting on the countertop. Wooden tables remain recognizable behind him, with clear gaps between their edges. Warm ceiling light illuminates his face evenly without altering the room's established colors. A low room tone and a faint off-screen clink of crockery accompany the still composition. No other intelligible voices occur.
[Shot 2] At 00:03.000, a closer view retains the counter in the background. <character:cashier> looks toward the waiting area. <character:cashier> says, <d>[English <voice:cashier>]Your order is ready.</d> The cashier finishes and closes his mouth. The camera remains steady for the complete line, keeping his face unobstructed and avoiding a cut to the empty waiting area while he speaks. His expression is friendly but restrained, and his gaze stays directed just left of the lens toward the unseen customer. The counter edge remains horizontal across the bottom of the frame. His hands stay on the countertop rather than introducing a new gesture that could obscure his face. The background stays softly visible, preserving the same warm light and table arrangement.
[Shot 3] At 00:07.000, return to the medium shot. <character:cashier> waits with relaxed hands and a closed mouth. The camera returns to the established counter-height viewpoint without changing which side of the counter he occupies. His shoulders settle after the announcement, and his gaze remains on the waiting area. The room's low ambience continues without added dialogue or music. Keep the visible table edges, empty space on the left, and light on the uniform consistent with the opening. At the end of the clip he stays still, with no fresh gesture, mouth movement, or camera drift. Hold this same position through the end of the clip so the following clip can inherit a clear, settled state.

overall_soundscape:
Low room tone and faint cups touching saucers. Only the cashier produces intelligible speech during the explicit line.

non_diegetic_music:
N/A
```

## Complete example: saved character with a temporary speaker

This example requires an existing saved `hero` character with an image and attached voice audio, with compiler_audio_usage set to reference. Replace both forms of `hero` with the user's exact saved tag. The temporary cashier speaks first and receives the first Subject/Speaker identity; the hero follows. Do not predict either number in the authored prompt.

```text
[new_location]
<character:cashier = A cashier in a red uniform.>
<voice:cashier = A young male voice with a friendly tone.>
<location:coffee_shop = A cozy coffee shop with wooden tables.>

subject_definitions:
{hero}
<character:cashier>
<location:coffee_shop>

summary:
{hero} collects an order from <character:cashier> in <location:coffee_shop>.

detailed_description:
The target video uses a realistic, quietly observed cafe style with warm indoor light.
[Shot 1] At 00:00.000, a medium shot in <location:coffee_shop> shows {hero} standing LEFT of the counter and <character:cashier> behind it on the RIGHT. Both have closed mouths. The camera holds at chest height, showing their established spacing across the counter and enough of the wooden tables to make the location recognizable. The hero's supplied appearance and wardrobe remain unchanged; describe only the features visible from this angle. The cashier's red uniform stays unobstructed above the counter. Warm ceiling light falls evenly across the two positions, with no change of daylight direction between cuts. A faint cup clink and low room tone establish the space without adding intelligible background dialogue.
[Shot 2] At 00:03.000, frame only <character:cashier> with the counter visible. <character:cashier> says, <d>[English <voice:cashier>]Your order is ready.</d> The cashier finishes and closes his mouth. The camera remains steady for the complete line, keeping his face unobstructed and holding the same face through the whole line. His expression is friendly but restrained, and his gaze stays directed just left of the lens toward the unseen customer. The counter edge remains horizontal across the bottom of the frame. His hands stay on the countertop rather than introducing a new gesture that could obscure his face. The background stays softly visible, preserving the same warm light and table arrangement.
[Shot 3] At 00:07.000, frame only {hero}, retaining the wooden tables in the background. {hero} says, <d>[English §hero§]Thank you.</d> The hero finishes and closes their mouth. Keep the hero on the same side of the counter as before, with the angle clearly motivated by the established geography. The camera remains stationary during the whole line; hold this face through the whole line. The hero's expression softens briefly in thanks, with a small change in gaze toward the edge of the frame. Neither the supplied wardrobe nor the visible table layout changes. The underlying room tone remains consistent across the cut.
[Shot 4] At 00:10.000, return to the medium shot. {hero} remains LEFT of the counter and <character:cashier> remains on the RIGHT, both silent with closed mouths through the end of the clip. Restore the original counter-height framing and spacing. Their hands and shoulders settle without a new exchange or object transfer. Keep the warm light and visible table edges stable; hold this final composition with only quiet room tone, providing a clear state for a same-location continuation.

overall_soundscape:
Quiet room tone and faint cups touching saucers. One active speaking voice at a time, with no additional intelligible background speech.

non_diegetic_music:
N/A
```

For a text-only saved voice, keep the same header-tag format; the compiler substitutes its voice description. For a silent version, omit the hero's speech event and all voice tags; keep the entity definition and authored silent actions. Attached audio alone does not require an audio relationship or task header.
## Multi-prompt sequence delimiter — critical

When returning more than one prompt, separate individual prompts using ONLY this exact delimiter on its own line:

|

Do not write:

PROMPT 1
PROMPT 2
PROMPT 3
Scene 1
Scene 2
Clip 1
Clip 2
---
===
or any other prompt labels or separators.

The first prompt begins directly with its normal content, such as:

[new_location]
...

The next prompt begins immediately after the delimiter:

|
<location:example = ...>
...

The delimiter `|` is outside the five required sections and exists only to separate independently compiled prompts.

Each prompt on either side of `|` must remain fully self-contained and independently valid.

When splitting or revising an existing sequence, preserve the `|` delimiter exactly.

FINAL OUTPUT RULE:

MULTIPLE PROMPTS → ONE plain-text code block with each prompt separated by exactly:

|

Never add prompt numbers, prompt titles, scene labels, clip labels, explanatory text, or Markdown headings inside the code block.
## Validate and deliver

Before returning a prompt:

1. Confirm deterministic mode is the target. Preserve exact known saved tags, and declare all temporary references before the sections.
2. Check English section prose, the five headings and their order, a single-paragraph summary, a style opening before Shot 1, and feasible shot timestamps, especially for dialogue. Check that each line can finish naturally before the next shot or the clip ends. Put each used character/location/object entity exactly once in subject_definitions. Do not define voices as visible entities.
3. Remove manually authored runtime numbers, voice-binding blocks, and task headers. Keep semantic references in actions and voice tags inside language brackets.
4. Check the intended performer for each speaking turn and place its voice tag inside the language brackets. Preserve spoken words after the brackets. Keep events in playback order and omit retention_analysis.
5. Validate every prompt in isolation. For multi-prompt sequences, the ONLY valid sequence separator is a single `|` on its own line. Split at each `|` and pretend all earlier prompt declarations and definitions are unavailable. Never use labels such as `PROMPT 1`, `PROMPT 2`, `Scene 1`, or `Clip 1` as separators.
   TEMPORARY REFERENCES:
   - Every temporary character, voice, location, and object used anywhere in the prompt must have its complete `= description` declaration in that same prompt.
   - A declaration in an earlier prompt never satisfies this requirement.
   - Every used character, location, and object must have its own subject_definitions entry.

   LOCATION CONTINUITY:
   - Evaluate `[new_location]` from physical story geography, independently from declaration scope.
   - Repeating `<location:name = description>` because the compiler registry resets does NOT trigger `[new_location]`.
   - Consecutive prompts using the same location tag represent the same physical place and must not introduce `[new_location]`.
   - Add `[new_location]` only when the sequence actually enters a different physical location, including the initial location when required by the workflow.

   SHOT/SPEAKER ISOLATION:
   - Scan each `[Shot N]` independently.
   - Count the distinct characters with explicit dialogue events inside that shot.
   - The allowed count is 0 or 1.
   - If two or more different characters speak inside one shot, split their turns into separate sequential shots while preserving the original dialogue and staging. Set timestamps far enough apart for each complete line at a natural speaking pace, including pauses and a brief handoff beat; let each speaker finish before the next turn.
   - Multiple dialogue clauses from the same character may remain in one shot.
   - Keep listeners silent with closed mouths where useful.

   Then check scene geography, duration, silence, handoff timing, and location markers. Same-location continuation never exempts a prompt from temporary-reference redeclaration.
6. If local compiler execution is available, compile each complete clip against the real record mapping. Do not fabricate production records to make unknown tags pass. Inspect JSON mapping and resource errors; repair semantic source or node options rather than editing compiled slot numbers. Compilation checks syntax and allocation, not generated video/audio quality.

For prompt-only requests, return the complete authoring prompt or sequence in one plain-text code block, with no commentary inside it.
For a single prompt, output only that prompt.
For multiple prompts, separate prompts using a single `|` on its own line.
Do not add prompt numbers, titles, scene labels, clip labels, Markdown headings, or alternative delimiters.
Do not include example labels, compiled output, JSON diagnostics, or this skill's instructions in the node input.
