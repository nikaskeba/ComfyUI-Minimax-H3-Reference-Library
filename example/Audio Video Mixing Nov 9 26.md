# Audio Video Mixing

Restart ComfyUI, refresh the browser, and reload `Audio Video Mixing Nov 9 26.json` after updating the nodes.

- **Source Video + Audio – Advances per Prompt:** select or upload a video. Drag the start slider beneath the preview to set the start immediately. Use the one-frame/one-second buttons for precision, or scrub the video and click **Use playhead as start**. The time readout shows the selected position.
- Choose **video audio** or **custom audio**. Use **Upload custom audio…** to add and select a track, or choose one from `ComfyUI/input`, including subfolders. In custom-audio mode, use the audio player and its separate start slider to audition and set the audio position. `custom_audio_start_seconds` sets the audio position corresponding to the first delivered video frame.
- Separate prompts with `|`. The source advances by each prompt's requested duration. For example, `[s=4] First edit | [s=6] Second edit` delivers ten seconds, using consecutive source windows. Prompts without `[s=...]` use the workflow's default duration.
- In the edit-mask container, set `video_edit_ranges` and `audio_edit_ranges` independently: `0-2; 4.5-6`, or one pair per line. Times are seconds relative to each delivered clip, and the same range list applies to every prompt. The old start/end controls are hidden in this workflow. Range ends beyond the clip are clamped to its end; ranges beginning after it are ignored.
- The exact-length node removes H3 frame-grid padding after continuation trimming. Requested lengths are rounded to the nearest frame at 24 fps. Video edit boundaries follow H3 latent-token resolution.

Keep the connected timing inputs on the source node. They account for continuation context and settling frames. The selected video must contain the requested source windows; shorten the prompt list or durations if it does not. Short audio is padded with silence.

Original workflow backups are saved alongside the JSON as `.pre-mixing-fix.json.bak`.
