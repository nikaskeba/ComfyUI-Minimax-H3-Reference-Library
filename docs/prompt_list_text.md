# SKEBA Prompt List Text

Connect its STRING output wherever you previously used a multiline string. The downstream prompt separator remains `|`.

**Raw text** edits the complete list. **Formatted view** displays one timeline block per prompt; select a block to edit its sections. Use **+** to insert a blank 15-second prompt before, between, or after existing prompts.

Length writes `[s=x]`; Scene change adds/removes `[new_location]`. Missing lengths appear as **15s · default** without changing the string. Section titles are fixed in visual mode; use Raw text to change structure or add custom sections.

The timeline is one rich text box. Reference tags are highlighted; shot labels and dialogue controls sit inline. **+ Shot** inserts a shot marker at the cursor; adding/removing markers renumbers them in order. Removing a marker keeps its surrounding action text. **+ Dialogue** inserts editable language, optional speaker, and speech controls; its × removes that dialogue event. Raw output retains `[Shot N]` and `<d>[Language speaker]Words</d>` syntax.

Speaker accepts a saved `§voice§` tag, a temporary `<voice:name>` tag, a plain saved reference name, or an empty value for no voice reference. This does not create audio attachments. Unrecognized dialogue stays editable as literal text with a notice.

**+ Reference** opens a picker inside the node, listing references in the current prompt and selected library entries first. Search saved references and built-in characters, filter by type, and insert at the cursor. This inserts a tag only; add it to `subject_definitions:` too if required by your prompt. Empty opening content is hidden while Length and Scene change remain available.

Undo/Redo covers visual edits and insertion; Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z also work in Formatted view. History is local to the open editor and resets on workflow reload. Merely switching views never rewrites the prompt. Visual changes do not retime shots or validate dialogue duration.
