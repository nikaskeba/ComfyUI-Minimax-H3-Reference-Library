# Third-Party Notices

This combined package is distributed under GNU GPL version 3. The top-level
`LICENSE` contains the complete GPLv3 terms.

## SKEBA H3 Motion Context

The vendored `motion_context/` package is derived from
`ComfyUI-H3-Motion-Context-SKEBA`, copyright 2026 NikoDemon80, and was supplied
under GNU GPL version 3. Its upstream project is
https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context.

Changes made for this combined package:

- Moved the Python package, documentation, and core tests beneath
  `motion_context/`.
- Changed the five node menu categories to
  `Skeba AI Nodes - Motion Context`.
- Adapted one test path expression for Windows-compatible execution.
- Registered the original node identifiers through the combined package.

## Previously MIT-Licensed Components

The H3 reference-library and Skeba utility code that predated the GPLv3
consolidation retains its original MIT notice in `LICENSES/MIT.txt`. The
batching-node source retains its upstream MIT license in
`LICENSES/ComfyUI-batching-nodes-MIT.txt`. Those permissive grants remain
applicable to their respective original components; the combined distribution
as a whole is provided under GPLv3.
