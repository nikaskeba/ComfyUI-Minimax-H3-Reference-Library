# Talking avatar on a body and background

Use `example/talkingavatar3_image.json` for a still body image or
`example/talkingavatar3_video.json` for a moving person video. Both extend
`talkingavatar2.json` and keep its FlashHead portrait/audio path.

1. Choose a clear **Face portrait for FlashHead**. It must depict the same
   person as the body image or body video.
2. Choose a **Person body image/video** and a **Background image**. The body
   source determines the final canvas size. The background is resized to it.
3. The FlashHead output is split into frames, audio, and FPS. The new
   **SKEBA Talking Avatar Face-to-Body Composite** tracks the selected face in
   each body frame, aligns the generated face with five facial landmarks,
   segments the body, and places it over the background. The original
   FlashHead audio is added back to the final video.
4. Start with `region=face`; use `head` if the face-only patch is too small.
   Adjust `feather` to soften the patch. `face_index` selects a person from
   left to right in the first body frame.

The compositor accepts one still body frame or a frame batch. With video,
connect the body clip's FPS to `person_fps` and use a clip long enough to cover
the FlashHead output. FlashHead currently outputs at 25 FPS. A short body clip
fails clearly instead of repeating unrelated frames. When the face cannot be
tracked, the original person frame is shown without a generated face.

Automatic body cutout uses the installed
`models/ultralytics/segm/person_yolov8m-seg.pt`. A precomputed full-person
`MASK` can instead be connected to `person_mask` to skip that segmentation.
The mask should correspond to the body image/video, not the FlashHead crop.

This is a tracked composite. It follows position, scale, and in-plane rotation,
but it cannot reconstruct a face hidden behind an object or turn a frontal
FlashHead generation into a true profile view. Review those frames and use a
pose-aware model for large head turns or prolonged occlusion.
