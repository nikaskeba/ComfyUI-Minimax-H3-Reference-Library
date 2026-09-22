# File-backed video loops

## Live playlist

Click **Open Live Playlist** on **Skeba Save Clip to File**. Playlist publishing
is always enabled. The viewer opens in a separate browser tab and lists each clip as
soon as its save and manifest update finish. Select a timeline clip to play it and read
its prompt. Playback automatically advances through completed clips and waits for
new ones at the end; **Stop playback** stops that behavior. File transitions
are not guaranteed gapless. Generation is stopped using ComfyUI's normal
interrupt control, independently of playback.

The viewer polls every two seconds and streams files directly, without a final
combine or temporary preview copy. The separate `preview_clip` option still
controls the existing on-node preview. Registered projects persist in
`ComfyUI/user/h3_video_projects.json`, including projects stored in custom
absolute directories. This viewer is served by the same ComfyUI server and
uses its existing access controls. Only registered manifest clips are served.

The example enables the live playlist and connects the current authoring prompt
to the saving node. Its final Combine and Save Combined nodes are disabled;
the loop's completion output remains enabled. Completed clips remain playable
after generation is interrupted. Whole-clip redo is available through the separate workflow described below;
automatic loop resume is not implemented.

`Skeba Save Clip to File` replaces the per-clip Save Video node. Connect its
VIDEO output to the loop accumulator, and the loop's incoming accumulation to
its optional `accumulation` input. The first clip creates a unique directory
under the selected output folder; later clips use the same directory.
CRF defaults to 18 (lower means larger files and higher quality).

Enable `preview_clip` to watch each completed clip in the saving node while
the loop continues. This creates a temporary browser-compatible MP4 with audio,
copying the saved MP4 without re-encoding video or audio. The loop
still accumulates the original MP4 files. Disable it to skip this extra copy.
The updated example enables previews. Preview files use ComfyUI's temp folder,
including when the project is saved outside ComfyUI's output directory.

`output_folder` defaults to `skeba_clips`. Enter any folder relative to
`ComfyUI/output` (for example `Videos`), an absolute path (for example
`D:/Renders`), or leave it blank to use the output directory itself.
`project_name` adds an optional project subfolder. For example, output folder
`Videos` and project name `Episode 01` produces:

```
ComfyUI/output/Videos/Episode 01/2026-09-16_14-30-00_a1b2c3d4/
    clip_00001_....mp4
    clip_00002_....mp4
    combined_....mp4
    manifest.json
```

Each run receives a unique dated folder. All clips, normalized bookends, and
the final combined MP4 are bundled there. The first clip chooses the directory;
the accumulation keeps later clips in that same bundle. A downstream Save Video
node can still create an additional final export at its own configured location.

Clips are saved as MP4 with 8-bit H.264 video and stereo 48 kHz AAC audio at
192 kbps. Audio is converted through 16-bit PCM; mono becomes stereo,
missing audio becomes silence, and audio is trimmed/padded to the video length.
The output VIDEO object holds a filename, not decoded frames. Files are retained
for recovery and are never automatically deleted.

`Skeba Combine Video Clips` automatically uses FFmpeg when every accumulated
clip comes from this node. It copies their video streams and encodes the joined
audio to AAC in an MP4. Audio is decoded a frame at a time into a temporary WAV,
trimming each clip to its video duration so AAC padding does not accumulate at
joins. Unlike the previous FLAC intermediates, AAC is lossy and the final audio
undergoes another encoding pass. Optional starting/ending videos are individually
normalized to the body clips' resolution (letterboxed), frame rate, and audio
format. Body clips must already share resolution and frame rate. Existing
in-memory accumulations retain the previous behavior.

The final VIDEO is file-backed and can feed Save Video. Use MP4/H.264 without
an explicit quality override to allow ComfyUI to reuse the encoded streams.
FFmpeg must be on PATH; no downloads are performed. FFmpeg's concat list is
temporary and removed after assembly.

The optional multiline `prompt` input accepts the current loop prompt, or text
entered directly. It is stored verbatim in `manifest.json` alongside each clip's
filename, stable clip ID, index, measured frame count, FPS, duration, dimensions,
CRF, and previous-file link. Duration is measured from the saved video rather
than inferred from `[s=...]`, so continuation trimming is reflected accurately.
The manifest is updated atomically after each saved clip, even before final
assembly. Combined outputs record their ordered constituent files and bookend
roles. Existing concat text files from older runs are not removed.

This JSON provides the prompt/file index used by the playlist editor. Original
loop clips do not capture complete sampler/model/seed/reference state. Redo jobs
record their chosen template, seed, prompt, duration and neighbor selections. Connect the authoring prompt to preserve its reusable
tags, or the compiled prompt if recording the exact model text is preferred.

Seam Exposure Match seeks into the previous clip and retains only its last six
decoded frames for analysis. Latent continuation save/load is unaffected.

`example/workflow_sep15.json` is wired for this mode. Restart ComfyUI to register
the new node and reload the workflow. This removes full-video accumulation and
tensor concatenation, but the current clip and any intermediate outputs retained
by ComfyUI's execution cache still consume memory. Check RAM across several
iterations in a real generation run; this is not a global cache eviction feature.

## Manual assembly in Live Playlist

Playlist publishing is always enabled on Save Clip to File; the live_playlist switch has been removed. The viewer shows completed clips on a horizontal timeline. Create Video queues an assembly job for the current ordered clip list, then links to its final MP4. Clips arriving later are included only when you create another video. Jobs use the normal ComfyUI queue.

Use `example/Loop_Debug_Live_Playlist.json` for a generation workflow that finishes at Skeba Finish Live Playlist instead of Combine/Save Video. The loop still completes and saves every clip; no final video is created until requested in the viewer. Existing workflows with Combine/Save Video still assemble automatically until that endpoint is replaced.


## Timeline editing and clip redo

Select a timeline clip to inspect its saved prompt. Drag clips to reorder them,
use Remove selected to take them out of the sequence, and Undo / Redo edit to
restore timeline edits. These operations never delete media. The Timeline clip list also supports drag
reordering, move-up/down buttons and per-clip Remove. All saved project clips
remain in Project clips, including alternates and removed clips; drag them onto
the timeline/list to insert before or after a clip, or drop into an empty
timeline. Insert before / Insert after buttons remain available. Project-clip
previews play only that file; timeline playback continues to the next clip.
Create Video assembles a snapshot of the current timeline, including repeated
clips if you insert a clip more than once.

To enable generation of alternates:

1. Restart ComfyUI to register **Skeba Playlist Redo Input / Save**.
2. Open `example/Playlist_Redo.json` in a separate workflow tab. Review its model,
   LoRA, resolution and sampler settings; these start from the existing loop
   example. Keep the output resolution compatible with the project clips.
3. Click **Register redo workflow** on Skeba Playlist Redo Save and give it a
   name. Registration saves an executable snapshot under
   `ComfyUI/user/h3_playlist_templates`. Register again after changing settings.
4. In Live Playlist, select an active clip and click **Redo clip…**. Select the
   registered workflow, edit the saved authoring prompt, set the desired visible
   duration and seed, then queue the alternate. The seed starts randomized.
5. Review the new alternate and explicitly insert it. Remove the old occurrence
   if you prefer the new version. No original file is replaced.

Previous and next context are independent and initially off. Each accepts
5 / 22 / 39 / 56 frames (22 by default), with optional audio. Previous uses the
neighbor's ending frames; next uses its starting frames. Neighbors are captured
from the timeline when submitting, so later reordering cannot change a queued
job. The selected original clip supplies the prompt, not implicit visual context.
Keep reusable character tags in saved prompts so the reference compiler can
load their attachments again.

The redo workflow generates one clip in two passes. Both AV Connectors receive
the selected context and are bypassed when neither neighbor is used. The upscale
connector preserves upscaled endpoints. Finalize removes the hidden overlaps;
Explicit `[Shot N] At MM:SS` timestamps are shifted past the hidden starting
overlap for generation; the saved authoring prompt keeps its original times.
Redo Save trims remaining H3 grid padding to the requested visible duration
(rounded to a 24 FPS frame). That padding can affect the exact transition into a
next clip; test both-neighbor transitions with your model before a long run.
The example does not use loop Motion Context, settling frames, or context saves.

Jobs and alternatives persist in the project manifest across page refreshes.
Queued/running jobs can be canceled individually on ComfyUI versions providing
the per-job cancel endpoint; otherwise use the normal ComfyUI queue controls.
A server restart does not resume interrupted generation. Registration and queue
validation report missing nodes/models before sampling. Playback streams each
file separately and is not guaranteed gapless; Create Video produces the joined
export. Editing here operates on whole clips, without arbitrary in/out trimming.

### Replace a section or insert footage

Select a timeline clip, click **Edit Clip**, and choose **Replace section** or **Insert footage** in the editor. Drag the two handles on the single cut bar, enter start/end seconds, or set either boundary at the preview playhead. In insertion mode, equal start/end values cut nothing; selecting 4–9 seconds removes those five seconds before inserting the new footage. **Cut 0 seconds** collapses the range without changing the generated duration. Replacement defaults to the removed duration; insertion defaults to five seconds. You can change the generated duration independently in insertion mode.

Write a focused prompt for only the new footage, starting its timings at zero. The original prompt is prefilled in the editable prompt box and also displayed separately for reference. Switching edit modes preserves your prompt edits. Before and After references default on when enough retained footage exists, with independent audio toggles and 5/22/39/56-frame choices. The editor shows the effective frame count; unavailable sides are disabled. At a clip boundary, references come from the adjacent timeline clip. Removed footage is never used as context. Choose **Insert between clips** to generate a standalone clip at a saved boundary.

The save node removes generation padding, normalizes the new section to the source dimensions and frame rate, and assembles retained prefix → new section → retained suffix. Audio follows the same cuts with no automatic crossfade. Both the generated section and stitched alternate are saved; originals and the active timeline remain unchanged. Review the alternate and choose **Use alternate**, or **Insert at saved position** for a between-clip insertion. These actions can be undone. Changed source occurrences or insertion boundaries require manual placement. Retained footage may be re-encoded for accurate cuts; transition quality still depends on the model. Restart ComfyUI after installing this update.

Timeline clips have an × button to remove that occurrence without deleting the file. Drag saved project clips onto either half of a timeline clip to insert before or after it, or onto an empty timeline. Use **Delete file…** on a project clip to permanently remove its MP4 and all timeline occurrences after confirmation. Permanent deletion cannot be undone and is blocked while an active generation needs the clip.

### Start from external videos

Use **New project** to create an empty project under `output/h3_projects`, then **Import videos…** to select one or more local videos. Videos are uploaded sequentially, converted to browser-compatible H.264 MP4 with stereo 48 kHz audio, and appended to the timeline. Silent sources receive a silent audio track. Imports retain the source frame rate as a constant frame rate for accurate editing; source files stay untouched. Imported clips have no prompt: select **Edit Clip** and enter one to redo, replace, or expand the footage. The registered two-pass redo workflow is still required for generation.

**Pause** keeps the current playhead position; **Play** resumes it and continues through subsequent timeline clips. Click **+ Bridge** on a timeline clip to generate a new clip between it and the next clip. The editor selects both boundaries as references when available, defaults to five seconds and 22 context frames, and saves a standalone alternate. Review it and choose **Insert at saved position** to add it between those clips.
