# Generate voice descriptions

Use **Generate voice description** beside the voice description in the Reference Library, built-in character Voice popout, or RefMod editor. The generated text replaces the field; **Undo** restores it. Save normally to persist the text. Analysis never saves references or retrains RefMods.

Analysis uses up to the first 15 seconds (at least 0.3 seconds) of the selected audio. New uploads take priority over saved attachments. RefMods use their kept voice followed by included source sections in editor order, respecting Max voice seconds. Removed audio is excluded.

Stored RefMod voices require the audio VAE connected to **SKEBA RefMod Studio Create / Edit**. Open the library from that node; decoding runs through ComfyUI's queue and requires no video VAE. Uploaded audio is analyzed locally without a model.

The English description estimates acoustic pitch, brightness, texture, and delivery. It does not detect accents, gender, identity, or separate multiple speakers. Use a clean single-speaker recording and review the result; add known accent information manually as needed.

Generate uses deterministic perceptual labels rather than acoustic numbers, usually targeting 20–35 words. It selects up to three timbre traits and three delivery traits, plus pitch, emphasizing distinctive measurements with sufficient evidence. Short or uncertain recordings may produce less text rather than invented characteristics.

Ranking uses heuristic distances and evidence weights, not a calibrated population distribution. The analyzer measures internal pause lengths, phrase lengths and their variation, and volume contrasts within active audio. Leading/trailing silence is excluded from pause measurements; energy gaps shorter than 120 ms are joined. Several observed phrases are required before describing phrase regularity. These are energy-based estimates, not transcription or measured words per minute.

Spectral emphasis can distinguish rounded midrange from a pronounced upper-mid edge when supported by the measurements. Vocal intensity describes variation within the recording, not real-world loudness. Nasality, physical vocal placement, emotion, and storytelling intent are not inferred. Background music, compression, and microphone coloration can affect these estimates; a description alone does not guarantee generated voice identity. Review generated wording and add known accent or characteristic pronunciation manually.

The analyzer is adapted from `comfyui-easy-ui`'s Voice Reference Description implementation. Its original measurements are preserved, with additional phrasing and volume-variation measurements; Skeba's concise formatter replaces the original technical prose. The MIT copyright and license are included in `voice_analysis_vendor/LICENSE`.
