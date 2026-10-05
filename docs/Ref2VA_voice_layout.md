# Compiled voice-reference layout

Deterministic output places each character's audio definition immediately after its subject definition, preserving the character's authored wardrobe text. Audio numbering is unchanged: a Subject 1 can still own Audio 2. Unowned media definitions follow the subject/voice pairs.

The summary retains authored scene prose, adds the task prefix derived from the selected reference usages, and adds concise exclusive voice bindings when voice isolation is enabled. Generated audio retention uses a short timbre-and-delivery instruction. Explicitly reused audio keeps reuse wording. Existing authored retention entries remain intact; accents are not invented.

RefMod subject definitions omit visual `in <Video N>` / `in <Picture N>` wording. Ordinary media keeps these labels, including multiple pictures belonging to one subject. RefMod media still participates in text encoding and latent conditioning in the same numbered order.

Keep `refmod_subject_only` **off** to retain the explicit RefMod Audio bindings used by this layout. Turning it on retains its existing behavior of suppressing those audio instructions. Dialogue, source selection, subject/speaker numbering, cropping, and continuation processing are unchanged.
