# File-backed video loops

## Live playlist

Enable `live_playlist` on **Skeba Save Clip to File**, then click **Open Live
Playlist**. The viewer opens in a separate browser tab and lists each clip as
soon as its save and manifest update finish. Select a clip to play it and read
its prompt. **Play sequence** advances through completed clips and waits for
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
after generation is interrupted. This does not implement automatic generation
resume or rerolling; those still require matching latent checkpoints/settings.

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

This JSON provides a prompt/file index for future regeneration tools. It does
not yet capture the complete sampler/model/seed/reference state or implement
segment regeneration. Connect the authoring prompt to preserve its reusable
tags, or the compiled prompt if recording the exact model text is preferred.

Seam Exposure Match seeks into the previous clip and retains only its last six
decoded frames for analysis. Latent continuation save/load is unaffected.

`example/workflow_sep15.json` is wired for this mode. Restart ComfyUI to register
the new node and reload the workflow. This removes full-video accumulation and
tensor concatenation, but the current clip and any intermediate outputs retained
by ComfyUI's execution cache still consume memory. Check RAM across several
iterations in a real generation run; this is not a global cache eviction feature.
