# SKEBA Reference Subject Mask: temporal stability

The node now has three optional controls after `bridge_gap_frames`. Existing workflows keep their previous behavior because all three default to off.

- `optical_flow_gap_frames`: Fills a short missing run only when masks on both sides can be carried through the video frames and still agree. The node also checks for a likely camera cut. Start at **4**.
- `mask_persistence_frames`: Carries the last mask forward through a brief unresolved disappearance, using frame motion. Start at **2**. This can cover the wrong area if a person abruptly exits or another person crosses into the same place, so keep it short.
- `boundary_hysteresis`: Mixes the current mask edge with the previous motion-aligned edge, constrained to a narrow band around the current detection. Start at **0.20**. Set it to zero if it makes a fast-moving edge look soft.

The `status` output now counts `flow filled`, `persisted`, `bridged`, and `unmasked` frames. The `frame_data_json` output identifies the corresponding frames. Inspect these alongside the tinted `preview` before generating the inpainted video. A sustained occlusion, scene cut, or wrong identity match still requires a better detection or a manual mask; temporal controls do not establish identity.

## A subject turning away

For human tracks, the first visible face still establishes identity. After that, **whole person** follows an unambiguous person silhouette continuously even if the face is turned away. `max_track_gap` now counts missing or ambiguous body frames rather than the number of frames since the last frontal face. In **head** and **face** regions, the last confirmed region moves with optical flow while the same body remains selected; it is refreshed when the face is recognized again. The status reports these as `head tracked`. Lips still require a recognized face because a turned-away lip location cannot be inferred reliably.

The tracker intentionally leaves the mask empty if it cannot distinguish the target body from another person or if the subject exits. Flow tracking may drift during long occlusion or abrupt head motion; inspect the tinted preview around turns before inpainting.

In head mode, a propagated head region is discarded when most of it has moved outside the frame, preventing a small remnant from flickering over clothing. The head is reacquired when the face becomes visible again. This check does not invent a head when it is fully off-screen.

## Optional clothing lock

Camera-motion prediction of the body box was removed because it could switch to another person. `clothing_match` is an optional second check for body-only tracking. It records the torso appearance from the first face-confirmed frame, rejects a spatial match whose clothing differs, and may recover a nearby body after a short pan when its outfit is distinctive. It refuses ties between similarly dressed people. `clothing_similarity` defaults to 0.65; higher values are stricter and can cause empty frames under strong lighting or wardrobe changes. Face-confirmed matches still take precedence, so use a sound `identity_threshold` as well.

The [clothing-lock comparison workflow](../example/Minimax%20-%20Inpaint%20_%20Controlnet%20-%2011_9_26%20-%20clothing%20lock.json) enables the clothing check at 0.70 and raises face identity threshold from 0.12 to 0.28. Its original workflow is untouched. This lightweight color descriptor is not a full person re-identification model; two people wearing similar suits remain ambiguous and should stay unmasked rather than swap identities.

## Faster human tracking without dropping video frames

`detection_stride` defaults to **1**, which runs person and face detection on every frame. Setting it to **2** runs those detectors on every other frame and carries the selected mask across the intervening frame with optical flow. The output still contains one mask for every input frame. The status labels those frames `propagated`. This can save detector work, although optical flow adds its own cost; compare actual runtime on the same clip. It is available for human tracks. Object tracking retains its existing cadence.

The updated user workflow had `identity_threshold=0.12`, `person_confidence=0.15`, `max_track_gap=20`, `optical_flow_gap_frames=12`, and `mask_persistence_frames=6`. Those permissive settings can let an incorrect candidate or stale mask remain selected. The [stride-2 tuned comparison](../example/Minimax%20-%20Inpaint%20_%20Controlnet%20-%2011_9_26%20-%20stride%202%20tuned.json) uses **0.28 / 0.25 / 10 / 3 / 3 / 2 / 0.15**, with `mask_feather=2` and `detection_stride=2`. Start by comparing the preview and `frame_data_json` at each flicker, then adjust only the setting responsible for that frame type.

[`Minimax - Inpaint _ Controlnet - 11_9_26 - temporal mask.json`](../example/Minimax%20-%20Inpaint%20_%20Controlnet%20-%2011_9_26%20-%20temporal%20mask.json) is the comparison workflow. It retains the original detection settings and uses `bridge_gap_frames=4`, `optical_flow_gap_frames=4`, `mask_persistence_frames=2`, and `boundary_hysteresis=0.20`.
