---
name: skeba-minimax-prompts
description: Write and revise MiniMax H3 video prompt sequences for SKEBA's deterministic H3 Tagged Reference Prompt compiler, using saved and temporary semantic references with explicit dialogue and clip continuity.
metadata:
  updated: 9/23/2026 5:30 PM
---

# SKEBA MiniMax H3 prompt writing

Write authoring prompts for **H3 Tagged Reference Prompt** with **compiler_mode = deterministic**. This mode must be selected on the node; restarting ComfyUI does not change a saved legacy setting. Legacy mode leaves temporary tags unchanged.

The prompt writer owns the story, scene descriptions, dialogue, timing, and continuity. The compiler owns reference discovery, definitions, runtime numbering, and task headers. Preserve the user's creative intent and spoken words.

Use the four-section SKEBA format below. Do not generate `summary` or `retention_analysis`. Put appearance and continuity requirements directly in the relevant scene descriptions. This is a deliberate local variation from the official six-section guide, based on the user's render tests. Voice references go inside the dialogue's language brackets: `<d>[English §saved_tag§]Spoken words.</d>`. Do not describe that placement as an official MiniMax requirement.

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
| Temporary character | `<character:cashier>` | Character declaration in subject_definitions |
| Temporary voice | `<voice:cashier>` | Voice and matching character declarations in subject_definitions |
| Temporary location | `<location:coffee_shop>` | Location declaration in subject_definitions |
| Temporary object | `<object:cup>` | Object declaration in subject_definitions |

Preserve saved tag spelling exactly, including spaces and `_BC` suffixes. Do not invent a saved tag or assume a built-in character has an attached image/audio file. Confirm available resources from the supplied catalog or library when accessible. Missing saved identities needed by the user require clarification; incidental new characters can use temporary declarations.

Repeat semantic entity tags in action descriptions when referring to those entities. Repeated tags reuse one identity; they do not load another copy of the asset. The old rule to invoke a tag only once and then manually use Subject numbers no longer applies.

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

Write all temporary declarations directly inside `subject_definitions`, one per line. Each entity declaration also supplies its subject entry, so do not repeat a bare tag there. Use this format for all newly written prompts.

Use this compact form:

```text
subject_definitions:
<character:cashier = A cashier in a red uniform.>
<voice:cashier = A young male voice with a General American English accent and a friendly tone.>
<location:coffee_shop = A cozy coffee shop with wooden tables.>
<object:cup = A white ceramic coffee cup.>
```

Elsewhere in the prompt, reference resources without `= description`. Names may start with digits and contain Unicode letters, spaces, underscores, hyphens, and punctuation, for example `1920s_street` or `café entrance`. Keep spelling and case consistent; surrounding whitespace is trimmed. Names must be nonempty and cannot contain tag delimiters (`< > = [ ] { } §`), the prompt separator `|`, control characters, or line breaks. Types are exactly `character`, `voice`, `location`, and `object`, in lowercase. Descriptions must be nonempty literal prose without nested reference tags or angle brackets.

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

IMPORTANT: redeclaring a temporary location does NOT mean the story has entered a new physical location. Declaration scope and physical-location continuity are separate concepts. `[new_location]` is determined by story geography, not by whether the temporary location had to be redeclared for compilation.

## Four required sections

Each prompt contains these headings exactly once, in this order, with the colon and heading on their own line. Do not add titles, commentary, numbered prefixes, or additional section headings inside the prompt.

### subject_definitions

List saved characters, locations, and objects as `{saved_tag}` entries. For characters whose clothing matters to the scene, append a concrete `Wardrobe:` description on the same line (see below). Define temporary entities with `<type:name = Complete description.>` entries. Put each entity on a separate line exactly once; do not add a second bare temporary tag. The compiler turns each entry into its complete definition. Do not wrap a tag in a manually authored definition such as `is {tag}` or append another copy of the library description.

The compiler sorts these definitions by the assigned Subject number and places used voice relationships beside their owning subjects. Keep authoring semantic tags; do not predict or manually arrange runtime numbers.

Used whole-video and music references receive separate role definitions automatically, even when first invoked later. They may also be listed once as their saved tag in subject_definitions. Their physical slots do not become Subjects. An image used only as an entity's provenance does not need a separate Picture definition.

Declare temporary voices as `<voice:name = Voice description.>` in subject_definitions alongside their characters. They describe speech and do not create a visible Subject; do not add a second bare voice entry. Do not write `S1 VOICE:` blocks or manually bind speaker numbers. Explicit speech events supply the binding, and the compiler adds used saved-audio relationships automatically. Put the starting wardrobe beside the character tag in subject_definitions. Put posture, placement, and shot-specific changes in detailed_description or timeline.

### Scene-specific character wardrobe

Actively consider wardrobe when writing a scene: work, formal events, weather, costumes, and a recurring story outfit benefit from explicit clothing descriptions even when the character already has a likeness reference. Do not assume an identity tag specifies the desired outfit. Honor the user's outfit first; otherwise choose concrete scene-appropriate clothing when useful, preserving any outfit already established in the story.

Append `Wardrobe:` to the character's single subject_definitions entry. Describe visually important garments, colors, footwear, accessories, and layering. This supplements the likeness reference; do not duplicate its face/identity description or redefine the saved tag.

```text
subject_definitions:
{Michael Scott_BC} Wardrobe: wearing a crisp white long-sleeve business dress shirt, dark patterned necktie, dark charcoal business trousers, and black leather dress shoes. This outfit remains fixed throughout the scene.
```

Use the same approach for other saved character tags, including direct RefMod characters. For temporary characters, include the outfit in their inline character declaration. Do not force business clothing or invent an outfit change when it is irrelevant. For an intentional mid-scene change, describe the starting outfit here and show the change in the timeline instead of claiming it stays fixed.

### HARD RULE — CROSS-PROMPT WARDROBE LOCK

When a character has a story-specific outfit that must persist across multiple prompts, establish the outfit using one complete concrete wardrobe description.

Repeat that exact complete wardrobe description beside the character's tag in `subject_definitions` of EVERY independently compiled prompt in which the character appears. It need not be duplicated in the opening `detailed_description`. Each prompt must contain the outfit in full even when the location, character reference, or video continuation stays the same.

Do not shorten later descriptions to phrases such as:

- "same outfit"
- "still wearing the outfit"
- "his normal clothes"
- "the previous wardrobe"
- "still wearing the vest"
- "unchanged clothing"

Instead, restate every visually important garment, color, footwear, accessory, and layering relationship. Reuse the established wording verbatim; do not introduce new details or synonyms that could imply a wardrobe change.

Example:

"{Cosmo Kramer_BC} Wardrobe: wearing a cream short-sleeve button-up shirt, dark brown trousers, black leather shoes, and a bright red sleeveless valet vest worn open over the shirt. This exact wardrobe remains fixed throughout the clip."

If the outfit intentionally changes, explicitly describe the new complete wardrobe at the point where the change begins. Otherwise, assume the established story wardrobe is locked across the sequence. For a change within a clip, describe the starting outfit in `subject_definitions` and the new complete outfit in the shot where it changes; use that new description in later prompts. Do not claim the outfit stays fixed throughout a clip that intentionally contains a change.

Keep the opening wardrobe descriptions separate from dialogue shots. In each speaking shot, describe only the active character and any relevant visible outfit details; do not repeat another character's wardrobe there. This is an authoring rule, not a new compiler validation requirement.

### Shot timing and cuts

Do not timestamp `[Shot 1]`; it begins at the start of the clip.

For a prompt beginning with `[new_location]`, Shot 1 establishes the new location and initial composition normally.

For a prompt WITHOUT `[new_location]`, Shot 1 is also the continuation handoff shot. Its opening frames must acknowledge the preceding prompt's final visible composition because the workflow supplies the final 22 frames of that clip as context. Begin Shot 1 from the inherited visible subject, framing, pose, and camera state before transitioning to a different subject or composition.

Do not treat 00:00 of a continuation as a fresh cut that has already occurred. If the desired opening composition differs from the inherited final shot, author the transition explicitly.

If the next speaker differs from the character visible in the inherited frames, prefer:

`[Shot 1] Live-action, cinematic, the inherited framing begins on only {Character_A}, preserving the preceding clip's final composition. The shot holds briefly without new dialogue.`

`[Shot 2] At 00:01.000, camera cuts to only {Character_B} in the established location. The new framing settles before {Character_B} speaks.`

Begin later shots with strictly increasing cut times inside the `[s=x]` duration:

`[Shot 1] Live-action, cinematic, a medium-wide shot frames...`

`[Shot 2] At 00:03.500, the camera cuts to...`

Use timestamps to allow dialogue and actions to finish naturally before the next cut. Set the next shot from the current line's natural speaking length rather than evenly dividing the clip.

Use `camera cuts to`, `shot cuts to`, `shot transitions to`, `shot changes to`, or `shot switches to` for ordinary cuts. Use cross-dissolve, fade, or wipe only when requested or narratively useful.

A cut should introduce meaningful new information about subject, space, state, viewpoint, or time. If only framing distance or a slight angle changes, prefer camera movement instead of a cut.

Set the next shot's start from the current line's natural speaking length, not from evenly divided shot intervals. Read the line at its intended delivery pace and allow for punctuation, pauses, emphasis, and any action before speech starts. Allow a natural pause before the cut through the shot timing; do not narrate the completion of speech or mouth closure. Slow, emotional, or hesitant delivery needs more time; do not force fast delivery just to meet a timestamp.

For example, a silent arrival at 00:00.000 followed by a speaker at 00:01.500 and the next speaker at 00:05.000 gives the first speaking shot 3.5 seconds. That spacing worked in the user's test; it is not a fixed allowance for every line. Longer dialogue needs a later cut. Give the final speaker enough time before the clip ends as well.

Use shot timing and the matching character/voice tags to establish dialogue handoffs. Do not append formulaic speech-completion or mouth-closure instructions after dialogue. Keep shots and speaking turns in playback order. Respect the requested overall clip length; if the dialogue cannot fit naturally, use fewer turns or split across clips when permitted, rather than crowding the timestamps or silently changing the spoken words. Untimed shots remain acceptable when precise timing adds no value or the user requests natural untimed pacing.

### detailed_description

Use `timeline:` on its own line in every complete prompt, after the opening description and before `[Shot 1]`. Leave a blank line on each side. It stays inside `detailed_description`; the prompt still has four top-level sections. The compiler accepts older prompts without this separator, but newly authored prompts should include it.

Before `timeline:`, describe the overall presentation, location, visual style, and persistent appearance or scene conditions. After `timeline:`, place the chronological shots, timed actions, camera changes, and dialogue. Do not put dialogue events in the opening description or use `timeline:` as a replacement for `detailed_description:`.

### Visual style, camera, and movement

At the beginning of `[Shot 1]`, state the overall visual style and initial composition. Use concrete style language such as `Live-action, cinematic`, `2D animation`, `3D CG`, `claymation`, `watercolor`, or `vintage film`.

When useful, specify the camera system, lens, support, lighting, and palette:

`[Shot 1] Live-action, cinematic, shot on an ARRI Alexa with a Cooke S4 75mm prime, a medium-wide composition under cold blue-green arctic lighting with a slightly desaturated palette.`

Use precise camera terminology:

- `Zoom In / Zoom Out` — lens changes focal length; camera stays stationary.
- `Push In / Pull Out` — camera moves forward/backward.
- `Pan Left / Pan Right` — camera pivots horizontally.
- `Truck Left / Truck Right` — camera moves horizontally.
- `Tilt Up / Tilt Down` — camera pivots vertically.
- `Pedestal Up / Pedestal Down` — camera moves vertically.
- `Arc Shot` — camera moves around the subject.
- `Tracking Shot` — camera follows a moving subject.
- `Static Shot` — camera and lens remain still.
- `Shake Slightly / Shake Strongly` — controlled camera shake.
- `POV` — subject's point of view.
- `Roll Clockwise / Roll Counterclockwise` — camera rolls around the lens axis.

Qualify movement when useful with `small/large amplitude` and `slow/fast speed`, e.g. `a slow push in with small amplitude`.

Do not add technical camera specifications merely to make a prompt sound cinematic. Use them when they provide meaningful visual direction and keep them consistent across shots unless a change is intentional.
Begin with one or two English sentences establishing presentation/style before `[Shot 1]`. Use sequential `[Shot N]` labels and encourage timestamps, especially for dialogue; follow the natural speaking-length guidance above before placing each cut. For each shot establish composition, visible appearance and positions, environment and lighting, actions/state changes, camera movement (type, amplitude, speed when relevant), current sound, and where references take effect. At an important entity's first visible appearance, describe the referenced characteristics actually visible in that shot. Do not reduce this section to plot or reference mappings.

For generation prompts, normally aim for 350-500 English words here. Dialogue-heavy scenes prioritize a feasible complete spoken timeline over reaching that range. Editing detail scales with the changes. One shot alone is not a reason to omit necessary detail; do not invent additional action to pad a word count. Write events in playback order, because the compiler assigns speakers in source order rather than sorting timestamps.

Use semantic tags for entities in actions and speech. Additional staging belongs before or after the speech pattern, not inserted inside its required structure.

### Prefer specific visual direction

Avoid vague prestige/style language such as `award-winning`, `high quality`, or a generic `modern anime style`. Describe what should actually be visible.

Prefer specific production, era, medium, studio, director, film, or series references when they communicate the intended look:

`Japanese animation inspired by [specific studio/director/series], with early-2000s digital coloring and restrained character animation.`

The detailed description should remain grounded in visible or audible information: visual style, composition, subject appearance and position, environment, props, action, reaction, camera behavior, dialogue, and synchronized diegetic sound.

### overall_soundscape

Describe diegetic sound: room tone, footsteps, clothing, cups, doors, impacts, weather. Do not repeat full dialogue. For alternating speech, describe one active voice at a time using ordinary prose; do not author S-number labels or place voice tags here merely because a character owns audio.

### non_diegetic_music

Describe audience-only music with instrumentation, tempo, and dynamic development, or write `N/A`. A supplied music resource uses its saved `{music_tag}` and must have a real audio file. Do not use character voice tags or a visual `{video_tag}` as music resources. If a synchronized video soundtrack actually supplies the score layer, cite `§video_tag§` and state whether that layer is copied or referenced. Describe ambience/effects layers in overall_soundscape and audience-only score in non_diegetic_music, even when they share one source.

## Dialogue and voice guidance

### Explicit accent for voices without audio references

When creating a temporary or otherwise text-described voice without an audio reference, specify its accent explicitly in the complete voice description. Language alone, such as `[English]`, does not define an accent. Tone, age, emotion, and delivery also do not replace an accent: "warm," "intimate," or "speaking quietly through a phone" still leaves pronunciation unspecified.

Choose a concrete accent consistent with the user's character and setting, such as "General American English accent" or "contemporary standard Southern British English accent." Follow an accent the user has specified; otherwise establish a suitable explicit accent when authoring the character. Avoid vague labels such as "European accent," and do not infer accent solely from appearance.

For a recurring voice, repeat the exact complete voice declaration, including the accent, inside subject_definitions in EVERY independently compiled prompt where it speaks. Preserve that accent across the sequence unless the story intentionally changes it. Phone filtering, whispering, or emotional changes should not silently change the established accent.

Example:

`<voice:woman = A young adult female voice with a General American English accent, a warm intimate tone, gently teasing and emotionally familiar, speaking quietly through a phone.>`

Use that same declaration in each applicable prompt, then reference it in dialogue as `<d>[English <voice:woman>]Spoken words.</d>`. Inline voice descriptions without a temporary voice tag must also name an accent. This is an authoring consistency rule, not a guarantee of identical generated voices or a new compiler validation requirement.

Use the language-header placement above for saved and temporary voices. A character without a voice reference can still speak with an inline description, for example `<character:guest> says in a cheerful voice with a General American English accent, <d>[English]Hello.</d>`. No audio file is invented. Natural delivery verbs and action clauses are accepted; `says` is a useful convention rather than a compiler requirement.

Keep each complete spoken turn with its intended performer. The compiler discovers speakers in first-vocal-event order and gives them matching Subject/Speaker numbers. Write events in playback order. A voice tag in a language header can identify a speaker even when surrounding prose is unconventional. Music and video soundtrack cues do not automatically become character speakers.

`compiler_voice_isolation` is an optional prompt augmentation, not a validation gate. Set it to false when testing the compact header format without additional generated voice-exclusion prose. The new voice syntax does not require that option. Do not author numbered ownership or exclusion rules yourself.

Use `<scenetrans>` and `<cutoff>` only for intentionally continuous dialogue across a cut or intentionally truncated speech. For ordinary turn-taking, finish the line before the next shot. Keep each entire dialogue block on the same speaking face when practical.

### Prefer simple one-pass dialogue rotation

For multi-character dialogue, optimize the scene structure for reliable speaker and voice binding before optimizing for conversational back-and-forth.

When three or more referenced characters speak in a short clip:

1. Prefer ONE speaking turn per character whenever the scene can still communicate the intended joke or story beat.
2. Prefer a simple forward speaker sequence, `A → B → C`, over a returning sequence, `A → B → C → A`.
3. Avoid returning to an earlier speaker merely to add a reaction line, tag line, or explanation. If the final joke can be assigned naturally to the last speaker in the rotation, prefer that structure.
4. Reduce the total number of dialogue handoffs. For a roughly 15-second clip, prefer 2–3 speaking shots rather than 4–5 short speaking shots when multiple referenced voices are active. This is a pacing preference, not a requirement to give every visible character dialogue.
5. Give every speaking shot enough uninterrupted time for the complete line, with enough time before changing speakers. Do not schedule rapid cuts simply to increase the number of jokes.
6. Make each character's dialogue strongly characteristic of that character's immediate role, attitude, or concern. Avoid generic lines that could plausibly belong to several characters in the scene.
7. Use silent multi-character establishing or reaction shots separately from dialogue shots. Establish who is present and the physical situation silently, then begin the one-character-per-shot dialogue rotation.
8. If a scene is experiencing voice or identity mixing, simplify in this order: remove unnecessary dialogue turns; eliminate return turns to previous speakers; increase time between speaker changes; shorten individual lines; strengthen character-specific wording.
9. Do not preserve an extra dialogue turn solely because conventional conversation would normally require a response. A separate silent visual reaction can provide the conversational beat without introducing another voice event. Do not automatically add audience laughter after dialogue.

PREFERRED:

- Silent establishing shot with A, B, and C.
- Shot 2: A speaks and completely finishes.
- Shot 3: B speaks and completely finishes.
- Shot 4: C speaks and delivers the final joke.

`A → B → C`

AVOID WHEN POSSIBLE:

- Shot 1: A speaks.
- Shot 2: B speaks.
- Shot 3: C speaks.
- Shot 4: A speaks again.
- Shot 5: B adds another reaction.

`A → B → C → A → B`

The second structure creates additional speaker re-entry and voice handoffs. Use it only when the story genuinely requires the additional exchange. This is an authoring preference, not a compiler validation rule. When revising supplied dialogue, preserve explicitly fixed words and speaker assignments; do not silently cut or reassign required dialogue just to achieve a one-pass rotation.

### Keep dialogue endings free of automatic follow-up prose

Do not routinely append phrases such as "completely finishes speaking and closes his mouth" or "The studio audience erupts into laughter" after a dialogue block. The user has observed more cross-talk with these endings. Let the shot end at `</d>` when no specific subsequent action is needed; do not replace the removed phrases with another repetitive instruction about stopping speech.

Maintain natural dialogue timing, matching voice tags, and speaking-shot character isolation. Include a post-dialogue action only when it serves the requested story. Audience laughter is not a default consequence of a joke or sitcom style; include it only when specifically requested or deliberately required by the scene, and describe general laugh-track treatment in overall_soundscape rather than appending it to every line.

### Maximum two dialogue sentences per shot

Keep intelligible dialogue to a maximum of TWO sentences per `[Shot N]`, counted across all dialogue blocks in that shot. The user has observed audio drift with longer turns. This limit applies to spoken dialogue, not scene descriptions or action sentences.

Split longer turns at sentence boundaries into additional sequential shots, even when the same character continues speaking. Preserve the spoken words and repeat the correct speaker and voice tag in each shot. Allow natural speaking time, pauses, and a brief closing beat before each cut. Two long sentences may still need separate shots; the sentence limit does not replace the timing check. Do not merge sentences or change punctuation just to evade the limit.

### HARD RULE — SPEAKING-SHOT CHARACTER ISOLATION

When a referenced character speaks, the speaking shot must visually and semantically isolate that character from all other characters.

For every dialogue shot:

1. The speaking character must be the ONLY character referenced anywhere inside that `[Shot N]`.
2. Do not show, name, describe, or reference any other character in that shot.
3. Do not mention another character as off-camera, unseen, silent, listening, reacting, nearby, or outside the frame.
4. Bind the dialogue directly to the visible character using matching character and voice tags: `{Character} says, <d>[English §Character§]Dialogue.</d>`. Use matching temporary tags for temporary references; retain inline voice descriptions for characters without a voice reference rather than inventing an audio attachment.
5. Repeat the matching voice tag for every new dialogue event.
6. Let dialogue end at `</d>` without automatically appending speech-completion, mouth-closure, or audience-laughter prose. Schedule enough time for the complete line before the next shot.
7. If another character needs to reply, cut to a NEW shot that visually isolates that character before their dialogue begins.
8. Multi-character shots should preferably be silent reaction, establishing, or action shots. Do not use them as speaking shots when reliable voice identity is important.
9. Do not place another character's name inside a speaking shot merely to describe who the speaker is addressing. Use neutral direction such as `looks toward the edge of frame`.
10. When voice-reference confusion has occurred or is likely, prioritize speaker isolation over conversational shot composition.

Keep the maximum of two spoken sentences per shot and allow natural speaking time before each cut. A continuing speaker still needs the matching tags in each new shot. Location and object references remain allowed: isolate the speaker from other characters, not from the environment. This is an authoring rule; it does not add compiler validation errors. Preserve user-supplied spoken words; apply the prohibition on naming other characters to staging prose and reference tags, not by silently rewriting dialogue that addresses someone by name.

GOOD:

[Shot 1] a medium shot shows only {George Costanza_BC} seated on the sofa inside {Jerry_Seinfeld_Apartment}. {George Costanza_BC} says, <d>[English §George Costanza_BC§]I'm not going!</d>

[Shot 2] At 00:03.000, a medium shot shows only {Jerry Seinfeld_BC} standing near the kitchen counter inside {Jerry_Seinfeld_Apartment}. {Jerry Seinfeld_BC} says, <d>[English §Jerry Seinfeld_BC§]You're going.</d>

BAD:

[Shot 1] George sits on the sofa while Jerry watches from the kitchen. {George Costanza_BC} says, <d>[English §George Costanza_BC§]I'm not going!</d>

BAD:

[Shot 1] A medium shot shows only {George Costanza_BC}. Jerry is off-camera listening. {George Costanza_BC} says, <d>[English §George Costanza_BC§]I'm not going!</d>

The same omission rule applies to silent shots explicitly framed around only one character. Other characters may still be defined in subject_definitions and appear in other shots.

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

## Scene duration with [s=x]

Use `[s=x]` before `subject_definitions` to request the current clip's duration in seconds, for example `[s=5]`, `[s=15]`, or `[s=12.5]`. It may share a line with `[new_location]`. The marker is optional; when absent, the workflow's configured duration applies. It is preserved for the workflow script to extract and apply, not automatically converted into a generation length by the compiler.

Choose duration per story beat instead of assuming every prompt is 15 seconds. A 5-second silent intro can be followed by 15-second dialogue clips. Repeat the chosen duration in each prompt; a previous `[s=5]` must not be treated as a persistent setting for later prompts. A duration change alone does not require `[new_location]`.

Keep timestamps local to each clip, starting at 00:00.000, and fit every action and complete spoken line within its duration. Use fewer shots and less description for a short intro; do not compress a 15-second dialogue exchange into five seconds. Continue to repeat complete temporary definitions and any locked wardrobe in every applicable prompt.

Example of a 5-second intro followed by a 15-second scene in the same location:

```text
[new_location] [s=5]

subject_definitions:
<location:coffee_shop = A cozy coffee shop with wooden tables.>
<object:coffee_cup = A small white porcelain coffee cup on a matching saucer, containing partially finished black coffee.>

detailed_description:
Warm natural light and a quiet observational style inside <location:coffee_shop>.

timeline:

[Shot 1]  a slow push toward <object:coffee_cup> on a wooden table inside <location:coffee_shop> establishes the setting through the end of the five-second clip.

overall_soundscape:
Quiet room tone and faint crockery sounds.

non_diegetic_music:
N/A
|
[s=15]

subject_definitions:
<location:coffee_shop = A cozy coffee shop with wooden tables.>
<object:coffee_cup = A small white porcelain coffee cup on a matching saucer, containing partially finished black coffee.>
<character:cashier = A cashier in a red uniform.>
<voice:cashier = A young male voice with a General American English accent and a friendly tone.>

detailed_description:
Warm natural light and a quiet observational style continue inside <location:coffee_shop>.

timeline:

[Shot 1] a close view of <object:coffee_cup> on the wooden table continues the established scene.
[Shot 2] At 00:03.000, a medium shot shows only <character:cashier> behind the counter inside <location:coffee_shop>. <character:cashier> says, <d>[English <voice:cashier>]Your order is ready.</d>
[Shot 3] At 00:08.000, the camera returns to <object:coffee_cup>, with the sunlit wooden table filling the background through the end of the clip.

overall_soundscape:
Quiet room tone and faint crockery sounds.

non_diegetic_music:
N/A
```

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
subject_definitions:
<location:bar = A dim neighborhood bar with a long wooden counter...>

Prompt 2:
subject_definitions:
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
### HARD RULE — SAME-LOCATION SPATIAL CONTINUITY

When consecutive prompts take place in the same physical location, the opening state of the later prompt must be a direct physical continuation of the final state of the preceding prompt. Treat the final shot of Prompt N as the authoritative starting state for Prompt N+1. In the user's continuation workflow, the next generation receives 22 frames from the preceding clip; write the opening as a continuation of that handoff, not a fresh arrangement of the scene. This frame count describes the workflow, not a universal MiniMax requirement.

Before writing Prompt N+1, inspect Prompt N's final shot and carry forward all visually important spatial state:

- each character's position in the room;
- whether each character is sitting, standing, reclining, walking, or otherwise posed;
- the furniture or architectural feature each character is beside, on, or near;
- orientation and facing direction when visually important;
- important objects being held, worn, or placed in the scene;
- doors being open or closed;
- important furniture and object state;
- persistent lighting and environmental state;
- story-specific visual changes such as glowing eyes, damage, wet clothing, removed jackets, or moved props.

The first shot of Prompt N+1 must begin from this inherited physical state. Carry forward the last established state of a character or object even if it is outside the final shot's framing; absence from the frame does not reset its position. Do not invent an unobserved change. When actual rendered handoff frames are supplied, reconcile the continuation with their visible state rather than assuming the previous render exactly followed its prompt.

Do NOT reposition a character between prompts merely because the new prompt needs a different composition.

If Prompt N ends with:

"{Jerry Seinfeld_BC} sits forward on the sofa while {robot} stands near the dining area."

Prompt N+1 should begin with:

"{Jerry Seinfeld_BC} remains seated forward on the sofa while {robot} stands near the dining area."

It must NOT arbitrarily begin with:

"{Jerry Seinfeld_BC} stands near the kitchen while {robot} stands near the center of the room."

unless the timeline first shows Jerry getting up and walking from the sofa to the kitchen and the robot moving from the dining area. These are staging fragments; use actual saved tags or fully declared temporary characters in complete prompts.

**CAMERA CHANGE ≠ SUBJECT MOVEMENT.** A cut from a wide shot to a medium shot, close-up, reverse angle, or another camera position must preserve the subject's established physical position unless movement is explicitly shown. Ground positions in room features rather than assuming screen-left stays screen-left across a reverse angle.

If the story requires movement during a same-location continuation:

1. Begin the new prompt in the inherited position.
2. Show the movement chronologically in the timeline.
3. Describe the character at the new position only after that movement occurs.

Never hide unexplained repositioning inside the opening shot. Ongoing motion should continue naturally from the inherited pose and direction; continuity does not require freezing a moving character.

For dialogue shots, preserve the inherited position while following SPEAKING-SHOT CHARACTER ISOLATION. Carry the overall scene state in the opening detailed_description, before timeline, or establish it in a separate silent shot. Do not list other characters inside a speaking shot merely to preserve their positions.

GOOD, when Jerry was last seated on the sofa:

"[Shot 2] A medium shot shows only {Jerry Seinfeld_BC} seated forward on the sofa inside {Jerry_Seinfeld_Apartment}."

BAD, unless the movement has already been shown:

"[Shot 2] A medium shot shows only {Jerry Seinfeld_BC} standing near the kitchen inside {Jerry_Seinfeld_Apartment}."

Do not use "same position as before" as a substitute for concrete state. Each prompt compiles independently: restate actual positions, poses, props, and persistent changes. Glowing eyes, damage, or a removed jacket must already be present at 00:00.000 of the next clip unless explicitly reversed. Keep the wardrobe lock consistent with intentional changes.

**SAME LOCATION + CONSECUTIVE PROMPTS = CONTINUOUS PHYSICAL BLOCKING**, unless the story explicitly establishes a time jump, discontinuous edit, or character movement. A time jump or discontinuous edit needs an explicit transition and compatible workflow handling; do not assume the inherited 22 frames disappear, and do not misuse [new_location] for an unchanged physical location.
### HARD RULE — CONTINUATION HANDOFF SHOT

When a prompt does NOT begin with `[new_location]`, assume its opening frames inherit the final 22-frame video context from the preceding prompt. The new prompt is still compiled independently, but its opening visual state is not independent.

The inherited 22 frames are the literal starting image of the next generation. `[Shot 1]` must therefore begin from what is visibly present in the preceding prompt's FINAL shot before introducing a different character, framing, or action.

Before writing a same-location continuation, inspect the preceding prompt's FINAL shot and identify:

- the visible character or characters;
- framing and camera angle;
- visible character position and pose;
- important visible props and environment;
- whether the visible character has just spoken;
- whether the camera is moving or holding stable.

Then apply these rules:

1. `[Shot 1]` must begin on the inherited visible subject and composition. Do not declare a different character as already being on screen at the start of the new generation.
2. Preserve the inherited framing briefly enough to create a clear visual handoff before changing subjects when necessary.
3. If the next story beat belongs to another character, explicitly transition from the inherited subject using `camera cuts to`, `camera pans to`, `camera trucks to`, or another visible camera transition.
4. The new character may speak only AFTER that transition has established the new character's shot.
5. Never assign dialogue to a newly introduced character while the inherited visual context still contains the preceding visible speaker. This can associate the new voice or dialogue with the inherited face.
6. When speaker identity is important, prefer a short silent handoff:

   inherited speaker/shot → explicit camera transition → new speaker established → new speaker dialogue.

7. The handoff requirement applies to what is VISIBLE in the inherited final shot. The broader SAME-LOCATION SPATIAL CONTINUITY rule still preserves the established physical state of characters and objects outside that framing.
8. `[new_location]` resets this inherited visual handoff requirement because the workflow is intentionally entering a different physical location.

Example:

Previous prompt ends:

`[Shot 4] ... only {George Costanza_BC} ... {George Costanza_BC} says, <d>[English §George Costanza_BC§]Nah, I ain't Jewish, I just don't dig on swine, that's all.</d>`

BAD continuation:

`[Shot 1] only {Jerry Seinfeld_BC} is visible. {Jerry Seinfeld_BC} says, <d>[English §Jerry Seinfeld_BC§]Why not?</d>`

The inherited frames still visibly contain George, so this creates a visual and speaker-identity conflict.

GOOD continuation:

`[Shot 1] Live-action, cinematic, the inherited close view begins on only {George Costanza_BC} seated inside {Monks_Coffee}, preserving his position and framing from the preceding clip. The shot holds briefly after his answer without new dialogue.`

`[Shot 2] At 00:01.000, camera cuts cleanly to only {Jerry Seinfeld_BC} seated in his established position inside {Monks_Coffee}. The new framing settles on Jerry before he speaks. {Jerry Seinfeld_BC} says, <d>[English §Jerry Seinfeld_BC§]Why not?</d>`

The 22-frame context is a VISUAL HANDOFF, not merely continuity guidance. The first authored shot must bridge from that inherited image into the new clip.
## Complete example: temporary resources only

This example can compile without any saved library entries. It intentionally creates no physical media slots.

```text
[new_location] [s=15]

subject_definitions:
<character:cashier = A cashier in a red uniform.>
<voice:cashier = A young male voice with a General American English accent and a friendly tone.>
<location:coffee_shop = A cozy coffee shop with wooden tables.>


detailed_description:
The target video uses a realistic, quietly observed cafe style with warm indoor light.

timeline:

[Shot 1]  a medium shot inside <location:coffee_shop> shows <character:cashier> standing behind the counter under soft indoor light. Only the cashier is visible. The camera is at counter height, with the cashier just RIGHT of center and the empty waiting area on the LEFT. The red uniform is clearly visible from the chest upward; the cashier keeps his shoulders relaxed and both hands resting on the countertop. Wooden tables remain recognizable behind him, with clear gaps between their edges. Warm ceiling light illuminates his face evenly without altering the room's established colors. A low room tone and a faint off-screen clink of crockery accompany the still composition. No other intelligible voices occur.
[Shot 2] At 00:03.000, a closer view retains the counter in the background. <character:cashier> looks toward the waiting area. <character:cashier> says, <d>[English <voice:cashier>]Your order is ready.</d> The camera remains steady for the complete line, keeping his face unobstructed and avoiding a cut to the empty waiting area while he speaks. His expression is friendly but restrained, and his gaze stays directed just left of the lens toward the edge of frame. The counter edge remains horizontal across the bottom of the frame. His hands stay on the countertop rather than introducing a new gesture that could obscure his face. The background stays softly visible, preserving the same warm light and table arrangement.
[Shot 3] At 00:07.000, return to the medium shot. <character:cashier> waits with relaxed hands and a closed mouth. The camera returns to the established counter-height viewpoint without changing which side of the counter he occupies. His shoulders settle after the announcement, and his gaze remains on the waiting area. The room's low ambience continues without added dialogue or music. Keep the visible table edges, empty space on the left, and light on the uniform consistent with the opening. At the end of the clip he stays still, with no fresh gesture, mouth movement, or camera drift. Hold this same position through the end of the clip so the following clip can inherit a clear, settled state.

overall_soundscape:
Low room tone and faint cups touching saucers. Only the cashier produces intelligible speech during the explicit line.

non_diegetic_music:
N/A
```

## Complete example: saved character with a temporary speaker

This example requires an existing saved `hero` character with an image and attached voice audio, with compiler_audio_usage set to reference. Replace both forms of `hero` with the user's exact saved tag. The temporary cashier speaks first and receives the first Subject/Speaker identity; the hero follows. Do not predict either number in the authored prompt.

```text
[new_location] [s=15]

subject_definitions:
{hero}
<character:cashier = A cashier in a red uniform.>
<voice:cashier = A young male voice with a General American English accent and a friendly tone.>
<location:coffee_shop = A cozy coffee shop with wooden tables.>


detailed_description:
The target video uses a realistic, quietly observed cafe style with warm indoor light.

timeline:

[Shot 1] a medium shot in <location:coffee_shop> shows {hero} standing LEFT of the counter and <character:cashier> behind it on the RIGHT. Both have closed mouths. The camera holds at chest height, showing their established spacing across the counter and enough of the wooden tables to make the location recognizable. The hero's supplied appearance and wardrobe remain unchanged; describe only the features visible from this angle. The cashier's red uniform stays unobstructed above the counter. Warm ceiling light falls evenly across the two positions, with no change of daylight direction between cuts. A faint cup clink and low room tone establish the space without adding intelligible background dialogue.
[Shot 2] At 00:03.000, frame only <character:cashier> with the counter visible. <character:cashier> says, <d>[English <voice:cashier>]Your order is ready.</d> The camera remains steady for the complete line, keeping his face unobstructed and holding the same face through the whole line. His expression is friendly but restrained, and his gaze stays directed just left of the lens toward the edge of frame. The counter edge remains horizontal across the bottom of the frame. His hands stay on the countertop rather than introducing a new gesture that could obscure his face. The background stays softly visible, preserving the same warm light and table arrangement.
[Shot 3] At 00:07.000, frame only {hero}, retaining the wooden tables in the background. {hero} says, <d>[English §hero§]Thank you.</d> Keep the hero on the same side of the counter as before, with the angle clearly motivated by the established geography. The camera remains stationary during the whole line; hold this face through the whole line. The hero's expression softens briefly in thanks, with a small change in gaze toward the edge of the frame. Neither the supplied wardrobe nor the visible table layout changes. The underlying room tone remains consistent across the cut.
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

The delimiter `|` is outside the four required sections and exists only to separate independently compiled prompts.

Each prompt on either side of `|` must remain fully self-contained and independently valid.

When splitting or revising an existing sequence, preserve the `|` delimiter exactly.

FINAL OUTPUT RULE:

MULTIPLE PROMPTS → ONE plain-text code block with each prompt separated by exactly:

|

Never add prompt numbers, prompt titles, scene labels, clip labels, explanatory text, or Markdown headings inside the code block.
## Validate and deliver

Before returning a prompt:

1. Confirm deterministic mode is the target. Preserve exact known saved tags, and declare all temporary references directly in subject_definitions, with no separate declaration prefix or duplicate bare temporary entry.
2. Check English section prose, the four headings and their order, no summary or retention_analysis, and `timeline:` on its own line before Shot 1. Shot 1 has no timestamp and establishes the overall style and initial composition. Later shots use strictly increasing timestamps within the clip duration. Check that dialogue and actions can finish naturally before the next cut.
3. Remove manually authored runtime numbers, voice-binding blocks, and task headers. Keep semantic references in actions and voice tags inside language brackets.
4. Check the intended performer for each speaking turn and place its voice tag inside the language brackets. Preserve spoken words after the brackets. Keep events in playback order and omit retention_analysis.
5. Validate every prompt in isolation. For multi-prompt sequences, the ONLY valid sequence separator is a single `|` on its own line. Split at each `|` and pretend all earlier prompt declarations and definitions are unavailable. Never use labels such as `PROMPT 1`, `PROMPT 2`, `Scene 1`, or `Clip 1` as separators.
   TEMPORARY REFERENCES:
   - Every voice without an audio reference must explicitly name an accent. Repeat each recurring voice's complete declaration verbatim, including its accent, in every prompt where it speaks.
   - Every temporary character, voice, location, and object used anywhere in the prompt must have its complete `= description` declaration in that same prompt.
   - A declaration in an earlier prompt never satisfies this requirement.
   - Every used character, location, and object must have its own subject_definitions entry.

   WARDROBE CONTINUITY:
   - For every appearing character with a persistent story-specific outfit, repeat the exact complete established wardrobe description beside that character's entry in `subject_definitions`.
   - Do not require the wardrobe to be duplicated in the opening `detailed_description`.
   - Reject shorthand such as "same outfit," "still wearing the vest," or "previous wardrobe" as a substitute.
   - Check garments, colors, footwear, accessories, and layering against the established outfit. Reuse the established wording verbatim unless an intentional story change occurs.
   - If the outfit intentionally changes, establish the complete new wardrobe when the change occurs and carry that exact description forward in subsequent prompts.

   CLIP DURATION:
  - Use [s=x] for intentionally selected scene lengths. Shot 1 begins implicitly at the start of the clip without a timestamp; all later shot timestamps must fit within that duration.

   LOCATION CONTINUITY:
   - Evaluate `[new_location]` from physical story geography, independently from declaration scope.
   - Repeating `<location:name = description>` because the compiler registry resets does NOT trigger `[new_location]`.
   - Consecutive prompts using the same location tag represent the same physical place and must not introduce `[new_location]`.
   - Add `[new_location]` only when the sequence actually enters a different physical location, including the initial location when required by the workflow.

   SAME-LOCATION SPATIAL CONTINUITY:
   - Compare Prompt N's final shot with Prompt N+1's opening shot when the physical location is unchanged. Internally list each active character's and important object's final established state.
   - Verify the next prompt starts with those concrete positions, poses, facing directions, prop placements, door states, and persistent visual changes. Use supplied handoff frames to check actual visible state when available.
   - Reject unexplained movement between furniture or room areas, standing/seated changes, and moved objects. A camera-angle change does not permit repositioning.
   - When movement is required, begin from the inherited position and show the movement before using the new position. Persistent changes such as glowing eyes must already be present at 00:00.000 unless explicitly reversed.
   - Preserve speaking-shot isolation: other characters' continuity belongs in the scene opening or separate silent shots, not inside another character's dialogue shot.
   
   CONTINUATION HANDOFF:
   - For every prompt without `[new_location]`, compare `[Shot 1]` directly against the preceding prompt's FINAL shot.
   - Identify the character(s) actually visible in that final shot, its framing, camera angle, visible pose/position, important props, and whether the camera is moving or holding.
   - Treat that final composition as the literal starting image supplied to the new generation by the 22-frame continuation context.
   - Verify that Shot 1 BEGINS from that inherited visible subject and composition before transitioning elsewhere.
   - Reject a continuation that starts by declaring a different character already on screen while the inherited frames visibly contain the preceding character.
   - If the next story beat or speaker differs from the inherited visible subject, require an explicit camera cut, pan, truck, or other visible transition before establishing the new subject.
   - If the next speaker differs from the inherited visible speaker, require a silent visual handoff before the new dialogue: inherited subject → camera transition → new speaker established → dialogue.
   - Never place the new speaker's dialogue into the inherited composition before that speaker has been visually established.
   - Apply SPEAKING-SHOT CHARACTER ISOLATION after the handoff: once the new speaker's dialogue begins, that speaking shot may reference only that speaker as a character.
   - Distinguish visible handoff continuity from broader spatial continuity: characters outside the inherited final framing retain their established physical positions even though Shot 1 should not mention them merely to preserve state.
   
   DIALOGUE ROTATION:
   - For short clips with three or more referenced speakers, prefer one turn each in a forward sequence, with 2–3 speaking shots in roughly 15 seconds where the story permits.
   - Remove unnecessary return turns before tightening cut timing. Keep necessary exchanges and fixed dialogue, allow enough time for each complete line, and use separate silent shots for multi-character reactions.

   SHOT/SPEAKER ISOLATION:
   - Scan each `[Shot N]` independently.
   - Count the distinct characters with explicit dialogue events inside that shot.
   - The allowed count is 0 or 1.
   - If two or more different characters speak inside one shot, split their turns into separate sequential shots while preserving the original dialogue and staging. Set timestamps far enough apart for each complete line at a natural speaking pace, including pauses and a brief handoff beat; let each speaker finish before the next turn.
   - Count spoken sentences across all dialogue blocks in the shot: the maximum is two. Split longer turns into additional shots at sentence boundaries, preserving the dialogue, speaker, voice tag, and natural timing. Multiple clauses from the same character may remain only within this limit.
   - In every speaking shot, count all characters shown, named, described, or referenced in staging prose, not just speakers: only the speaking character is allowed. Remove off-camera/listener mentions, repeat matching voice tags for every dialogue event, and omit automatic speech-completion, mouth-closure, or laughter endings. Put multi-character reactions in separate silent shots.

   Then check scene geography, duration, silence, handoff timing, and location markers. Same-location continuation never exempts a prompt from temporary-reference redeclaration.
6. If local compiler execution is available, compile each complete clip against the real record mapping. Do not fabricate production records to make unknown tags pass. Inspect JSON mapping and resource errors; repair semantic source or node options rather than editing compiled slot numbers. Compilation checks syntax and allocation, not generated video/audio quality.

For prompt-only requests, return the complete authoring prompt or sequence in one plain-text code block, with no commentary inside it.
For a single prompt, output only that prompt.
For multiple prompts, separate prompts using a single `|` on its own line.
Do not add prompt numbers, titles, scene labels, clip labels, Markdown headings, or alternative delimiters.
Do not include example labels, compiled output, JSON diagnostics, or this skill's instructions in the node input.
