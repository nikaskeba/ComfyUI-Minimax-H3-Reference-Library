# Compiled voice-reference layout

Deterministic output places each character's audio definition immediately after its subject definition, preserving the character's authored wardrobe text. Audio numbering is unchanged: a Subject 1 can still own Audio 2. Unowned media definitions follow the subject/voice pairs.

The summary retains authored scene prose, adds the task prefix derived from the selected reference usages, and adds concise exclusive voice bindings when voice isolation is enabled. Generated audio retention uses a short timbre-and-delivery instruction. Explicitly reused audio keeps reuse wording. Existing authored retention entries remain intact; accents are not invented.

RefMod subject definitions omit visual `in <Video N>` / `in <Picture N>` wording. Ordinary media keeps these labels, including multiple pictures belonging to one subject. RefMod media still participates in text encoding and latent conditioning in the same numbered order.

Keep `refmod_subject_only` **off** to retain the explicit RefMod Audio bindings used by this layout. Turning it on retains its existing behavior of suppressing those audio instructions. Dialogue, source selection, subject/speaker numbering, cropping, and continuation processing are unchanged.

## Reference ordering test

In deterministic mode, `compiler_reference_order=first_speech` preserves the existing speaker-first subject/media order. Select `library_order` to use media priority and library insertion order (temporary declaration order for temporary references), independently of first speech. Speaker IDs still follow first dialogue occurrence. The prompt-list validator exposes the same setting.

For a controlled continuation comparison, use the same reference set and speaking characters in adjacent prompts, and inspect the `mapping` output. A second-speaking character can now remain Subject 1 / Audio 1 while becoming S2. This is not a persistent cross-prompt slot registry: missing references and silent characters' omitted voice clips can still change numbering. Legacy mode is unchanged. Compare both modes using the same seed and continuation settings; this option does not establish that slot changes cause voice swaps.

Character audio definitions include the saved voice description as 'Voice characteristics: ...' after the existing ownership binding. This applies to reference and reuse audio, with either reference ordering mode. Empty descriptions add nothing, and silent characters do not gain audio references.
