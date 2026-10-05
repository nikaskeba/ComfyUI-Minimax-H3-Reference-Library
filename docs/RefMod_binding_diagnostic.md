# RefMod binding diagnostic

To audition a prepared voice, connect Apply's **conditioning** to **SKEBA H3 Reference Audio Preview**, connect the H3 audio VAE, and select `audio_number` matching the diagnostic's ordinal. Connect its **audio** output to Preview Audio or Save Audio (prefer WAV). This works for ordinary and RefMod audio and decodes the post-crop/post-Apply latent without loudness normalization. It does not load the original uncropped recording or change the sampler conditioning. Tagged Reference Prompt's direct audio sockets are empty when RefMods force deferred loading, even for ordinary audio in the same bundle.

Connect **SKEBA Apply H3 RefMod → reference diagnostic** to a Display Any/text node. The existing conditioning and curve-graph outputs keep their original positions. Restart ComfyUI and refresh the browser after updating.

For each conditioning entry, the JSON lists final reference blocks in order. Bound SKEBA RefMods include their tag, file/member, channel, compiler subject and speaker, expected audio number, binding identifier, audio tensor shape and approximate duration. `audio_ordinal` counts actual audio-bearing blocks, including existing native audio/video soundtracks. `audio_order_matches_compiler: false` indicates an order mismatch worth investigating.

Compare this report with Tagged Reference Prompt's `mapping` output and its `voice_assignments`. Numbers for subject, speaker and audio need not equal each other. Missing ownership for native or external unbound references is reported explicitly, not guessed. Legacy compiler mode does not supply deterministic subject/speaker assignments.

This is an inspection of Apply's output, not proof that the model will use the intended voice or that downstream nodes leave conditioning unchanged. It does not modify reference tensors or generation settings. Audio duration uses H3's 40 latent steps per second.
