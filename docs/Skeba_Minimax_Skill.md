---
name: skeba-minimax-prompts
description: Write and revise MiniMax H3 video prompt sequences for SKEBA's deterministic H3 Tagged Reference Prompt compiler, using saved and temporary semantic references with explicit dialogue and clip continuity.
---

# SKEBA MiniMax H3 prompt writing

Write authoring prompts for **H3 Tagged Reference Prompt** with **compiler_mode = deterministic**. This mode must be selected on the node; restarting ComfyUI does not change a saved legacy setting. Legacy mode leaves temporary tags unchanged.

The prompt writer owns the story, scene descriptions, dialogue, timing, retention instructions, and continuity. The compiler owns reference discovery, definitions, runtime numbering, voice relationships, and summary task headers. It also fills a missing character voice-timbre retention entry when its meaning is mechanically known; other retention decisions remain authored. Preserve the user's creative intent when revising a prompt; do not change dialogue or staging just to repair syntax.

The supplied Full-Reference Mode Rewrite Output Format Guide governs the final six-section output. Our saved/temporary tags are an authoring layer that compiles to that output; do not paste the guide's already-numbered examples into deterministic mode. Write all six sections in English, preserving the original language of dialogue, lyrics, and visible scene text.

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

Repeat semantic entity tags in summary, retention, and action descriptions when referring to those entities. Repeated tags reuse one identity; they do not load another copy of the asset. The old rule to invoke a tag only once and then manually use Subject numbers no longer applies.

Use ordinary human-readable names when those names are spoken aloud. Do not emit caret/tilde legacy tags, backslash-escaped syntax, or HTML entities in place of literal `<`, `>`, `{`, `}`, or section signs.

## Temporary declarations

Put declarations before `subject_definitions`, one per line:

```text
<character:cashier = A cashier in a red uniform.>
<voice:cashier = A young male voice with a friendly tone.>
<location:coffee_shop = A cozy coffee shop with wooden tables.>
<object:cup = A white ceramic coffee cup.>
```

After this prefix, reference resources without `= description`. Names must start with an ASCII letter and contain only ASCII letters, digits, or underscores. Types are exactly `character`, `voice`, `location`, and `object`, in lowercase. Descriptions must be nonempty literal prose without nested reference tags or angle brackets.

Declare each type/name pair once per prompt. Temporary voice and character names must match. `<voice:cashier>` cannot voice `<character:customer>` or a saved character. Saved `{cashier}` and temporary `<character:cashier>` are different resources, even when their names match. Avoid reusing a temporary name across unrelated types.

Temporary resources are description-only. They do not create media inputs. Use declarations only for resources active in this clip.

## Every prompt is self-contained

Each prompt is compiled separately with a fresh temporary registry. Nothing declared or defined in Prompt 1 is available to Prompt 2. This applies to every clip, including direct same-location continuations without `[new_location]`. Inherited video frames carry visual state; they do not carry prompt declarations, definitions, or reference numbering.

For every individual prompt:

- Repeat the full `= description` declaration for every temporary character, voice, location, or object referenced anywhere in that prompt. Put these declarations before subject_definitions.
- Include each used character, location, and object tag once in that prompt's subject_definitions, including saved library entities. A previous prompt's definition does not count.
- Saved library entries remain available by their exact saved tags; do not recreate them as temporary declarations. Invoke them again in the current prompt so its compiler can discover their media and generate local definitions.
- Repeat the matching voice tag at every speaking event. If it is a temporary voice, repeat both its voice declaration and its matching character declaration in this prompt.
- Carry forward the full concrete description of a continuing temporary resource. Do not substitute “same as before,” “previously defined,” or a bare tag for its declaration. Keep identity details consistent and change state details only when the story requires it.

For example, if both Prompt 1 and Prompt 2 use a package, **both prompts** must contain this full declaration before their sections:

```text
<object:tegridy_package = A sealed commercial marijuana package labeled Tegridy Farms, with a printed 2D cartoon portrait of Randy Marsh and a transparent window revealing green marijuana inside.>
```

Both prompts must also include `<object:tegridy_package>` once in subject_definitions and use that tag for the package in their own actions and retention analysis. Prompt 2 needs this declaration even when the package is already visible in its inherited starting frames. In a real sequence, repeat the complete established package description, including any additional appearance constraints, rather than shortening it to this example.

## Six required sections

Each prompt contains these headings exactly once, in this order, with the colon and heading on their own line. Do not add titles, commentary, numbered prefixes, or additional section headings inside the prompt.

### subject_definitions

Place every active character, location, and object entity tag on a separate line, exactly once. The compiler turns each tag into its complete definition. Do not wrap a tag in a manually authored definition such as `is {tag}` or append another copy of the library description.

The compiler sorts these definitions by the assigned Subject number and places used voice relationships beside their owning subjects. Keep authoring semantic tags; do not predict or manually arrange runtime numbers.

Used whole-video and music references receive separate role definitions automatically, even when first invoked later. They may also be listed once as their saved tag in subject_definitions. Their physical slots do not become Subjects. An image used only as an entity's provenance does not need a separate Picture definition.

Temporary voices do not need their own definition line. Do not write `S1 VOICE:` blocks or manually bind speaker numbers. Explicit speech events supply the binding, and the compiler adds used saved-audio relationships automatically. Put shot-specific clothing, posture, and placement in retention and detailed description.

### summary

Write one short English paragraph describing the target video and its main reference relationships, using semantic entity tags. A known actual voice-audio reference can be cited with its section-sign tag, for example `The voice timbre of §hero§ guides {hero}.`; it compiles to an Audio label. Omit voice tags for text-only voices and omit full dialogue. Leave out bracketed task headers; the compiler computes them from actual media usage.

When a summary should be sorted by subject, write separate self-contained lines, each starting with an entity tag and mentioning only that entity. The compiler sorts this format by assigned Subject number, then joins the lines into one paragraph. The task header and paragraph share one line. For video editing, the compiler supplies the required opening identifying the edited source video. Ordinary narrative sentences involving multiple subjects keep their authored order; do not split an interaction merely to force sorting.

### retention_analysis

Author the desired retention behavior for each active entity using its semantic tag. Available visual relationship vocabulary includes `fully_preserved`, `partially_preserved`, `attribute_transfer`, and `weak_reference`. Include the shots or phases where the content applies, such as `{hero} (appears in [Shot 1], [Shot 3]): fully_preserved - retain the supplied identity.` State concretely what is retained or intentionally changed within the defined reference role. New actions, backgrounds, or plot events are not automatically losses of reference fidelity.

For used actual saved voice audio, a retention line can use `§saved_tag§: reference - retain the supplied voice timbre for {saved_tag}.` Only include it when that audio is intentionally used. For text-only voices, put the voice reference in the explicit speech event; a voice tag in retention otherwise disappears and can leave a dangling sentence. Do not invent numbered media retention entries. Include one retention line for every independently tracked Subject, whole-video reference, and used Audio reference; do not add a Picture line for image provenance alone. Audio markers are `fully_copy` (the complete final soundtrack is copied), `partially_copy` (selected time/layers or a modified mix), `reference` (signal not copied), and `weak_reference` (broad similarity). Do not use visual markers on audio or audio markers on visible entities. Never put Speaker IDs in retention. For a used character voice in reference mode, the compiler fills a missing Audio retention line with its known timbre/delivery relationship and exclusive Subject ownership. It leaves authored entries unchanged and reports remaining missing, duplicate, or invalid retention entries in mapping warnings. It does not guess full versus partial reuse, shot applicability, or visual retention.

### detailed_description

Begin with one or two English sentences establishing presentation/style before `[Shot 1]`. The opening shot has no timestamp. Later cuts use `[Shot N] At MM:SS.mmm, ...`. For each shot establish composition, visible appearance and positions, environment and lighting, actions/state changes, camera movement (type, amplitude, speed when relevant), current sound, and where references take effect. At an important entity's first visible appearance, describe the referenced characteristics actually visible in that shot. Do not reduce this section to plot or reference mappings.

For generation prompts, normally aim for 350-500 English words here. Dialogue-heavy scenes prioritize a feasible complete spoken timeline over reaching that range. Editing detail scales with the changes. One shot alone is not a reason to omit necessary detail; do not invent additional action to pad a word count. Write events in playback order, because the compiler assigns speakers in source order rather than sorting timestamps.

Use semantic tags for entities in actions and speech. Additional staging belongs before or after the speech pattern, not inserted inside its required structure.

### overall_soundscape

Describe diegetic sound: room tone, footsteps, clothing, cups, doors, impacts, weather. Do not repeat full dialogue. For alternating speech, describe one active voice at a time using ordinary prose; do not author S-number labels or place voice tags here merely because a character owns audio.

### non_diegetic_music

Describe audience-only music with instrumentation, tempo, and dynamic development, or write `N/A`. A supplied music resource uses its saved `{music_tag}` and must have a real audio file. Do not use character voice tags or a visual `{video_tag}` as music resources. If a synchronized video soundtrack actually supplies the score layer, cite `§video_tag§` and state whether that layer is copied or referenced. Describe ambience/effects layers in overall_soundscape and audience-only score in non_diegetic_music, even when they share one source.

## Explicit dialogue grammar

Every intelligible spoken line uses a language marker and literal speech inside `<d>...</d>`. Use English for newly authored dialogue by default. Preserve supplied dialogue/lyrics in their original language unless the user requests translation.

Saved character:

```text
{saved_tag} says §saved_tag§, <d>[English]Literal spoken words.</d>
```

Temporary character:

```text
<character:cashier> says <voice:cashier>, <d>[English]Your order is ready.</d>
```

The supported lowercase verbs are `says`, `asks`, `replies`, `whispers`, `shouts`, `sings`, `speaks`, and `exclaims`. Prefer `says`. Keep the entity, verb, voice tag, comma, and dialogue together in that order. For example, put “turns toward the counter” in a preceding sentence, rather than between the entity and `says`. Include the matching voice tag on every speaking turn, including repeated turns by the same character. For the same character off-screen, use `{saved_tag} (off-screen) says §saved_tag§, <d>[English]Hello.</d>` (or matching temporary tags); the compiler reuses the same speaker. This explicit authoring grammar is narrower than the guide's final rendered prose.

Inside dialogue, include only language metadata and words spoken aloud. No semantic tags, runtime labels, actions, camera instructions, or sound effects. A spoken mention of another character uses their readable name. Do not add reference tags to existing literal dialogue; move misplaced reference instructions outside it while preserving the spoken words.

Use a saved voice only if that saved character has audio or a voice description. Do not silently invent a missing saved voice or attach another character's voice. A temporary character can have a newly authored temporary voice description consistent with the user's premise. The compiler inserts text voice descriptions literally, so write fluent phrasing such as “a warm mid-pitched voice with a relaxed cadence.”

For direct reuse or explicitly requested reperformance, preserve source words and language; use `[unclear]` for genuinely unintelligible spans rather than guessing. Use basic punctuation with complete utterances ending before `</d>`. When revising user-supplied dialogue, do not silently change its words or translate it. When only voice timbre or delivery is referenced, do not import the source clip's dialogue. The compiler preserves dialogue literally and does not transcribe audio.

A verbal cue embedded in reused music/soundtrack is not automatically a new speaker: `When {music_tag} reaches <d>[English]Go!</d>, {hero} raises a hand.` Use an explicit character speech event if a person actually produces the voice. The compiler leaves such audio-only cues without a Speaker ID. `<scenetrans>` and `<cutoff>` are preserved control markers, not resource tags; do not invent their placement without a supplied example or the basic video guide. Prefer complete turns before cuts for the currently supported simple authoring path.

For clear turn-taking, finish a line before the next speaker begins. Keep non-speakers silent and their mouths closed when useful. Prefer a shot focused on the active speaking face when confusion is likely, especially if the line names another character or their catchphrase. Cut to a listener's reaction after the whole line finishes. These are staging preferences; honor an explicit request for overlap or different framing.

Replace vague shorthand such as “they chat” with explicit lines or visible silent actions when it would otherwise invite unintended speech. Do not let the compiler's lack of an error substitute for checking that every intended speaker has an explicit event.

## Voice-reference isolation

Keep `compiler_voice_isolation = true` (the default) for explicit ownership guidance. Each character voice clip applies only to its assigned Subject and Speaker. Its timbre, accent, cadence, pitch, and delivery must not transfer to another speaker, even during alternating dialogue, shared framing, or lines naming another character.

Continue authoring the normal semantic speech event. The compiler adds the numbered ownership statement before each event, repeats the owner's exclusive audio assignment, and tells other speakers not to use or imitate that clip. It uses the real allocation: the first Subject may be the second or third Speaker. Text-only speakers retain their own literal voice descriptions. Do not manually insert `S1 speaks` blocks, numbered exclusions, or guessed Audio ownership into compiler input.

Keep Speaker IDs out of retention_analysis, including negative exclusions. The official format uses Subject and Audio labels there; the compiler's generated voice-retention line follows that rule. Definitions and actual vocal events can include the global Speaker ID.

Do not apply character-voice exclusivity to score or synchronized soundtrack cues, and do not manufacture an Audio slot for a text-only voice. Do not add an unused voice reference just to mention its exclusion. These are prompt instructions, not an acoustic isolation mechanism; judge effectiveness with a generation comparison, using the isolation option to turn the extra wording off if necessary.

When drafting scenes, prefer a clear active speaking face with listeners silent or off-camera for confusing turns. A printed portrait, package image, or screen depiction is an object representation rather than another live character or vocal source unless the user explicitly requests otherwise. Describe the depicted identity and medium in its temporary object declaration; keep it out of the speaking-event list.

## Media and task ownership

The compiler discovers all used resources before allocating slots. Subject priority is image plus audio, image, audio, then description-only; ties use stable library order followed by temporary declaration order. Subject, Speaker, Picture, Audio, and Video numbers are independent and local to each prompt. Reusing the same semantic identity across clips does not guarantee the same number.

Actual media alone allocates physical slots. A voice description does not create an Audio slot, and speech alone does not imply an audio-reference task. A silent character can have an allocated audio file without a textual audio reference. Never force a voice tag onto a silent character just to account for their attached audio.

Music becomes an Audio reference, `{video_tag}` becomes a Video reference, and `§video_tag§` explicitly selects that video's enabled soundtrack; neither automatically becomes a Subject or speaker. A video's available soundtrack does not create an audio task/definition until explicitly used. A soundtrack-only tag does not imply editing or continuation of the visual track. Some Audio slots represent music or video soundtracks, so the old rule that every Audio slot belongs to a speaking character is incorrect. Enabled video soundtracks are numbered before standalone audio. Use the node's JSON `mapping` output to inspect actual ownership; never infer ownership from matching numbers.

Set task purpose using node options when the task calls for it:

- `compiler_video_usage = reference` or `motion_reference`: video supplies reference material; neither implies continuation.
- `compiler_video_usage = continuation` or `editing`: explicitly requests that video task.
- `compiler_audio_usage = reference` or `reuse`: describes how intentionally used audio is used.

These options apply across the prompt unless resource metadata overrides them. Same-location continuity through the workflow does not by itself mean a saved video is a continuation input. Do not write a task header to override node options. Audio used as generation guidance adds reference generation plus audio reference; directly reused audio adds audio reuse. Voice-reuse wording explicitly describes signal reuse rather than timbre-only guidance. Keyframe completion is not inferred by this compiler. A text-only prompt may have no task header; that is valid.

Current physical limits are 9 images, 3 standalone audio files, and 3 videos, including assets allocated for used silent characters. Do not drop requested references merely to fit: identify the limit and adapt the resource selection with the user when needed.

## Full-reference features outside the current authoring model

The official guide supports more reference relationships than this compiler currently models. Do not fake support by inserting runtime numbers or inventing new temporary types:

- Concrete first/key/last-frame anchors and standalone storyboard Picture roles need explicit asset-role inputs; ordinary entity images are provenance today.
- Several source assets defining one Subject, or several Subjects extracted from one source, need an explicit identity/source mapping. Separate saved tags currently remain separate resources.
- Independent narrators without a visible Subject and group speech need a dedicated vocal-source model. Do not create a visible character merely to obtain a speaker number.
- Per-shot reuse/reference changes for the same audio, or mixed purposes for several video assets, need role metadata beyond the global node options. Do not infer these from prose.

For those requests, identify the missing representation and adapt the workflow explicitly. Keep compiled runtime output separate from deterministic authoring input.

## Clip boundaries and continuity

For SKEBA sequence authoring, keep one physical location per clip. Use multiple angles and movement within that environment. Start a new clip for a different physical location unless the user explicitly requests another structure.

Use `[new_location]` as the first line when initializing a new location, normally including the first clip. Temporary declarations follow this marker, then the six sections. Do not use the marker for a close-up, camera change, entrance, same-location continuation, or same-location time jump. It is a workflow control marker, not a section or a video-task header.

For sequences consumed by a prompt-splitting workflow, put a single `|` on its own line between complete prompts. The workflow must split these before the tagged-reference node: the compiler accepts one six-section prompt per invocation. Do not use `|` inside descriptions or dialogue in that sequence format. For a single direct node input, omit the separator.

Preserve inherited character instances, wardrobe, positions, posture, held objects, mouth state, and nearby geometry in direct continuations. Do not make an already-present character enter again or duplicate them. Establish a same-location time/state jump immediately in Shot 1. For a location change, end the old clip in its old location and start the new clip already in the destination.

Use the workflow's configured duration and inherited-frame count. The previous skill's 15-second clips and 22-frame handoff are workflow defaults, not compiler guarantees. If no timing is specified, plan approximately 15 seconds with 2-5 shots. Keep timestamps within the chosen duration. For direct dialogue continuations, normally finish speech before the final 1-2 seconds and leave a short stable, closed-mouth handoff. Preserve that inherited state at the start of the next clip before a new action or speech event.

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

retention_analysis:
<character:cashier> (appears in [Shot 1], [Shot 2], [Shot 3]): fully_preserved - retain the red uniform.
<location:coffee_shop> (appears throughout): fully_preserved - retain the wooden tables and counter layout.

detailed_description:
The target video uses a realistic, quietly observed cafe style with warm indoor light.
[Shot 1] A medium shot inside <location:coffee_shop> shows <character:cashier> standing behind the counter under soft indoor light. Only the cashier is visible. The camera is at counter height, with the cashier just RIGHT of center and the empty waiting area on the LEFT. The red uniform is clearly visible from the chest upward; the cashier keeps his shoulders relaxed and both hands resting on the countertop. Wooden tables remain recognizable behind him, with clear gaps between their edges. Warm ceiling light illuminates his face evenly without altering the room's established colors. A low room tone and a faint off-screen clink of crockery accompany the still composition. No other intelligible voices occur.
[Shot 2] At 00:04.000, a closer view retains the counter in the background. <character:cashier> looks toward the waiting area. <character:cashier> says <voice:cashier>, <d>[English]Your order is ready.</d> The cashier finishes and closes his mouth. The camera remains steady for the complete line, keeping his face unobstructed and avoiding a cut to the empty waiting area while he speaks. His expression is friendly but restrained, and his gaze stays directed just left of the lens toward the unseen customer. The counter edge remains horizontal across the bottom of the frame. His hands stay on the countertop rather than introducing a new gesture that could obscure his face. The background stays softly visible, preserving the same warm light and table arrangement.
[Shot 3] At 00:11.000, return to the medium shot. <character:cashier> waits with relaxed hands and a closed mouth. The camera returns to the established counter-height viewpoint without changing which side of the counter he occupies. His shoulders settle after the announcement, and his gaze remains on the waiting area. The room's low ambience continues without added dialogue or music. Keep the visible table edges, empty space on the left, and light on the uniform consistent with the opening. During the final two seconds he stays still, with no fresh gesture, mouth movement, or camera drift. Hold this same position through 00:15.000 so the following clip can inherit a clear, settled state.

overall_soundscape:
Low room tone and faint cups touching saucers. Only the cashier produces intelligible speech during the explicit line.

non_diegetic_music:
N/A
```

## Complete example: saved character with a temporary speaker

This example requires an existing saved `hero` character with an image and attached voice audio, with compiler_audio_usage set to reference. Replace both forms of `hero` with the user's exact saved tag. The temporary cashier speaks first, even if media priority makes the saved hero the first Subject. Do not predict either number in the authored prompt.

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
{hero} collects an order from <character:cashier> in <location:coffee_shop>. The voice timbre of §hero§ guides the hero's reply.

retention_analysis:
{hero} (appears in [Shot 1], [Shot 3], [Shot 4]): fully_preserved - retain the supplied identity and wardrobe.
§hero§: reference - preserve the voice timbre without copying the original words or signal.
<character:cashier>: fully_preserved - retain the red uniform.
<location:coffee_shop> (appears throughout): fully_preserved - retain the wooden tables and counter layout.

detailed_description:
The target video uses a realistic, quietly observed cafe style with warm indoor light.
[Shot 1] A medium shot in <location:coffee_shop> shows {hero} standing LEFT of the counter and <character:cashier> behind it on the RIGHT. Both have closed mouths. The camera holds at chest height, showing their established spacing across the counter and enough of the wooden tables to make the location recognizable. The hero's supplied appearance and wardrobe remain unchanged; describe only the features visible from this angle. The cashier's red uniform stays unobstructed above the counter. Warm ceiling light falls evenly across the two positions, with no change of daylight direction between cuts. A faint cup clink and low room tone establish the space without adding intelligible background dialogue.
[Shot 2] At 00:03.000, frame only <character:cashier> with the counter visible. {hero} remains off-camera and silent. <character:cashier> says <voice:cashier>, <d>[English]Your order is ready.</d> The cashier finishes and closes his mouth. The camera remains steady for the complete line, keeping his face unobstructed and avoiding a cut to the hero while he speaks. His expression is friendly but restrained, and his gaze stays directed just left of the lens toward the unseen customer. The counter edge remains horizontal across the bottom of the frame. His hands stay on the countertop rather than introducing a new gesture that could obscure his face. The background stays softly visible, preserving the same warm light and table arrangement.
[Shot 3] At 00:07.000, frame only {hero}, retaining the wooden tables in the background. The cashier remains off-camera and silent. {hero} says §hero§, <d>[English]Thank you.</d> The hero finishes and closes their mouth. Keep the hero on the same side of the counter as before, with the angle clearly motivated by the established geography. The camera remains stationary during the whole line; do not cut to the cashier while the hero is speaking. The hero's expression softens briefly in thanks, with a small change in gaze toward the off-camera cashier. Neither the supplied wardrobe nor the visible table layout changes. The underlying room tone remains consistent across the cut.
[Shot 4] At 00:11.000, return to the medium shot. {hero} remains LEFT of the counter and <character:cashier> remains on the RIGHT, both silent with closed mouths through 00:15.000. Restore the original counter-height framing and spacing. Their hands and shoulders settle without a new exchange or object transfer. Keep the warm light and visible table edges stable; the final two seconds hold this composition with only quiet room tone, providing a clear state for a same-location continuation.

overall_soundscape:
Quiet room tone and faint cups touching saucers. One active speaking voice at a time, with no additional intelligible background speech.

non_diegetic_music:
N/A
```

For a text-only saved voice, remove the summary's audio-reference sentence and the voice retention line; keep the explicit speech event. For a silent version, omit the hero's speech event and all voice tags; keep the entity definition and authored silent actions. Attached audio alone does not require an audio relationship or task header.

## Validate and deliver

Before returning a prompt:

1. Confirm deterministic mode is the target. Preserve exact known saved tags, and declare all temporary references before the sections.
2. Check English section prose, the six headings and their order, a single-paragraph summary, a style opening before Shot 1, and no opening-shot timestamp. Put each used character/location/object entity exactly once in subject_definitions. Do not define voices as visible entities.
3. Remove manually authored runtime numbers, voice-binding blocks, and task headers. Keep semantic references in actions and retention.
4. Check every explicit speaking turn against the supported grammar and matching character/voice identity. Leave generated voice-isolation rules to the compiler, and keep Speaker IDs out of retention. Keep events in playback order and dialogue literal.
5. Validate every prompt in isolation: split at each sequence separator and pretend all earlier prompts are unavailable. Every temporary tag must have its own full declaration in that same prompt, and every used entity must have its own subject_definitions entry there. Then check scene geography, duration, silence and handoff timing, and location markers. Same-location continuation never exempts a prompt from this check.
6. If local compiler execution is available, compile each complete clip against the real record mapping. Do not fabricate production records to make unknown tags pass. Inspect JSON mapping, retention warnings, and errors; repair semantic source or node options rather than editing compiled slot numbers. Compilation checks syntax and allocation, not generated video/audio quality.

For prompt-only requests, return the complete authoring prompt or sequence in one plain-text code block, with no commentary inside it. Do not include example labels, Markdown headings, compiled output, JSON diagnostics, or this skill's instructions in the node input. If a missing saved resource or incompatible workflow setting prevents a usable result, explain that outside the prompt rather than hiding it in the six sections.
