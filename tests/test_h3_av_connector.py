import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import torch


ROOT = Path(__file__).resolve().parents[1]
COMFY_ROOT = ROOT.parents[1]
if str(COMFY_ROOT) not in sys.path:
    sys.path.insert(0, str(COMFY_ROOT))

SPEC = importlib.util.spec_from_file_location(
    "h3_av_connector_test", ROOT / "h3_av_connector.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def h3_latent(latent_frames=17, latent_height=4, latent_width=6):
    video = torch.zeros((1, 24, latent_frames, latent_height, latent_width))
    frame_count = sum(
        MODULE.FRAME_PER_TOKEN[index % 5] for index in range(latent_frames)
    )
    audio = torch.zeros((1, 32, 2, round(frame_count / 24 * 40)))
    return {
        "samples": SimpleNamespace(is_nested=True, tensors=(video, audio))
    }


def conditioning(existing=None):
    metadata = {}
    if existing is not None:
        metadata["minimax_keyframes"] = existing
    return [[torch.zeros((1, 1)), metadata]]


def image_batch(count, height=2, width=3):
    return torch.arange(float(count)).reshape(count, 1, 1, 1).expand(
        -1, height, width, 3
    ).clone()


def audio_value(seconds, sample_rate=24000, channels=2, offset=0.0):
    samples = int(round(seconds * sample_rate))
    values = torch.arange(float(samples)) + offset
    return {
        "waveform": values.reshape(1, 1, samples).expand(1, channels, -1).clone(),
        "sample_rate": sample_rate,
    }


class FakeVideoVAE:
    def __init__(self):
        self.inputs = []

    def encode(self, frames):
        self.inputs.append(frames.clone())
        count = int(frames.shape[0])
        latent_t = {5: 2, 22: 7, 39: 12, 56: 17}.get(count, 1)
        value = float(frames[0, 0, 0, 0]) + 100.0
        return torch.full((1, 24, latent_t, 4, 6), value)


class FakeAudioVAE:
    audio_sample_rate = 24000

    def __init__(self):
        self.inputs = []

    def encode(self, waveform):
        self.inputs.append(waveform.clone())
        latent_t = max(1, round(waveform.shape[1] / self.audio_sample_rate * 40))
        return torch.zeros((1, 32, 2, latent_t))


def metadata(result):
    return result[0][0][1]


class H3AVConnectorGuideTests(unittest.TestCase):
    def run_guide(self, **kwargs):
        kwargs.setdefault("positive", conditioning())
        kwargs.setdefault("latent", h3_latent())
        kwargs.setdefault("vae", FakeVideoVAE())
        with mock.patch.object(
            MODULE.h3, "_resize", side_effect=lambda frames, width, height, crop: frames
        ):
            return MODULE.SkebaMiniMaxH3AVConnectorGuideTest.execute(**kwargs)

    def test_bypass_does_not_request_lazy_inputs(self):
        positive = conditioning()
        latent = h3_latent()
        needed = MODULE.SkebaMiniMaxH3AVConnectorGuideTest.check_lazy_status(
            positive,
            bypass=True,
            latent=None,
            vae=None,
            audio_vae=None,
            start_frames=None,
            start_audio=None,
        )
        self.assertEqual(needed, ["latent"])
        result = MODULE.SkebaMiniMaxH3AVConnectorGuideTest.execute(
            positive=positive, latent=latent, bypass=True
        )
        self.assertIs(result[0], positive)
        self.assertTrue(result[1]["bypass"])
        self.assertIs(result[3], latent)

    def test_second_pass_can_explicitly_replace_an_existing_noise_mask(self):
        latent = h3_latent()
        latent["noise_mask"] = object()
        with self.assertRaisesRegex(ValueError, "Replace Existing Noise Mask"):
            self.run_guide(
                latent=latent,
                start_frames=image_batch(22),
            )

        result = self.run_guide(
            latent=latent,
            start_frames=image_batch(22),
            replace_existing_noise_mask=True,
        )
        self.assertIn("noise_mask", result[3])
        self.assertIn("Replaced the incoming first-pass noise mask", result[2])

    def test_second_pass_can_pin_the_upscaled_latent_without_overwriting_it(self):
        latent = h3_latent()
        original_video = latent["samples"].tensors[0].clone()
        result = self.run_guide(
            latent=latent,
            start_frames=image_batch(22),
            preserve_upscaled_endpoints=True,
        )

        pinned_video = result[3]["samples"].tensors[0]
        video_mask = result[3]["noise_mask"].tensors[0]
        self.assertTrue(torch.equal(pinned_video, original_video))
        self.assertTrue(bool((video_mask[:, :, :7] == 0).all()))
        self.assertIn("preserved from the upscaled input latent", result[2])

    def test_lazy_mode_requests_connected_media_and_matching_vaes(self):
        needed = MODULE.SkebaMiniMaxH3AVConnectorGuideTest.check_lazy_status(
            conditioning(),
            bypass=False,
            latent=None,
            vae=None,
            audio_vae=None,
            start_frames=None,
            start_audio=None,
        )
        self.assertEqual(
            needed, ["latent", "start_frames", "start_audio", "vae", "audio_vae"]
        )

    def test_start_uses_last_22_frames_and_matching_audio_tail(self):
        video_vae = FakeVideoVAE()
        audio_vae = FakeAudioVAE()
        frames = image_batch(24)
        audio = audio_value(2.0)
        target = h3_latent()
        result = self.run_guide(
            latent=target,
            start_frames=frames,
            start_audio=audio,
            start_overlap="22",
            vae=video_vae,
            audio_vae=audio_vae,
        )
        keyframe = metadata(result)["minimax_keyframes"][0]
        self.assertEqual(keyframe["resolved_frame_index"], 0)
        self.assertEqual(video_vae.inputs[0].shape[0], 22)
        self.assertEqual(float(video_vae.inputs[0][0, 0, 0, 0]), 2.0)
        wanted = round(22 / 24 * audio_vae.audio_sample_rate)
        self.assertEqual(audio_vae.inputs[0].shape, (1, wanted, 2))
        self.assertEqual(float(audio_vae.inputs[0][0, 0, 0]), float(audio["waveform"][0, 0, -wanted]))
        self.assertEqual(result[1]["start"]["overlap"], 22)
        pinned_video, pinned_audio = result[3]["samples"].tensors
        video_mask, audio_mask = result[3]["noise_mask"].tensors
        self.assertEqual(pinned_video.shape, h3_latent()["samples"].tensors[0].shape)
        self.assertTrue(bool((video_mask[:, :, :7] == 0).all()))
        self.assertTrue(bool((video_mask[:, :, 7:] == 1).all()))
        self.assertTrue(bool((pinned_video[:, :, :7] == 102).all()))
        self.assertTrue(bool((target["samples"].tensors[0] == 0).all()))
        self.assertTrue(bool((audio_mask[..., :37] == 0).all()))
        self.assertTrue(bool((audio_mask[..., 37:] == 1).all()))

    def test_end_uses_first_frames_at_end_of_output(self):
        video_vae = FakeVideoVAE()
        frames = image_batch(24)
        result = self.run_guide(
            end_frames=frames,
            end_overlap="5",
            vae=video_vae,
        )
        frame_count = sum(
            MODULE.FRAME_PER_TOKEN[index % 5] for index in range(17)
        )
        keyframe = metadata(result)["minimax_keyframes"][0]
        self.assertEqual(keyframe["resolved_frame_index"], frame_count - 5)
        self.assertEqual(video_vae.inputs[0].shape[0], 5)
        self.assertEqual(float(video_vae.inputs[0][-1, 0, 0, 0]), 4.0)

    def test_end_audio_is_cropped_to_target_audio_timeline(self):
        audio_vae = FakeAudioVAE()
        result = self.run_guide(
            end_frames=image_batch(24),
            end_audio=audio_value(1.0),
            end_overlap="22",
            audio_vae=audio_vae,
        )
        keyframe = metadata(result)["minimax_keyframes"][0]
        # 56 video frames allocate 93 audio steps. Frame 34 begins at 56.67.
        self.assertEqual(keyframe["audio_latent"].shape[-1], 36)

    def test_two_sided_connector_is_chronological(self):
        result = self.run_guide(
            start_frames=image_batch(30),
            end_frames=image_batch(30),
            start_overlap="22",
            end_overlap="22",
        )
        indices = [
            keyframe["resolved_frame_index"]
            for keyframe in metadata(result)["minimax_keyframes"]
        ]
        self.assertEqual(indices, [0, 34])  # 17 latent steps cover 56 frames.

    def test_39_and_56_frame_context_lengths_use_complete_h3_spans(self):
        for count, latent_frames in ((39, 22), (56, 37)):
            with self.subTest(count=count):
                vae = FakeVideoVAE()
                result = self.run_guide(
                    latent=h3_latent(latent_frames=latent_frames),
                    start_frames=image_batch(60),
                    start_overlap=str(count),
                    vae=vae,
                )
                keyframe = metadata(result)["minimax_keyframes"][0]
                self.assertEqual(keyframe["resolved_frame_index"], 0)
                self.assertEqual(vae.inputs[0].shape[0], count)

    def test_short_media_and_audio_without_frames_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "has 4 frames"):
            self.run_guide(start_frames=image_batch(4), start_overlap="5")
        with self.assertRaisesRegex(ValueError, "start_audio requires start_frames"):
            self.run_guide(start_audio=audio_value(1.0), audio_vae=FakeAudioVAE())

    def test_short_audio_and_malformed_h3_latent_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "but a 22-frame overlap needs"):
            self.run_guide(
                start_frames=image_batch(22),
                start_audio=audio_value(0.25),
                audio_vae=FakeAudioVAE(),
            )
        with self.assertRaisesRegex(ValueError, "MiniMax H3 AV latent"):
            self.run_guide(
                latent={"samples": torch.zeros((1, 4, 4, 4))},
                start_frames=image_batch(22),
            )

    def test_mono_audio_is_normalized_to_stereo_for_h3(self):
        audio_vae = FakeAudioVAE()
        self.run_guide(
            start_frames=image_batch(5),
            start_audio=audio_value(1.0, channels=1),
            start_overlap="5",
            audio_vae=audio_vae,
        )
        self.assertEqual(audio_vae.inputs[0].shape[-1], 2)

    def test_existing_keyframe_collision_is_rejected_before_encoding(self):
        vae = FakeVideoVAE()
        old = {
            "resolved_frame_index": 10,
            "latent": torch.zeros((1, 24, 1, 2, 3)),
        }
        with self.assertRaisesRegex(ValueError, "collides with existing keyframe"):
            self.run_guide(
                positive=conditioning([old]),
                start_frames=image_batch(22),
                start_overlap="22",
                vae=vae,
            )
        self.assertEqual(vae.inputs, [])

    def test_overlaps_that_fill_short_output_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "start and end overlaps collide"):
            self.run_guide(
                latent=h3_latent(latent_frames=12),  # 39 output frames
                start_frames=image_batch(22),
                end_frames=image_batch(22),
            )


class H3AVConnectorFinalizeTests(unittest.TestCase):
    def connector_bundle(self, start=22, end=5):
        return {
            "version": MODULE.BUNDLE_VERSION,
            "bypass": False,
            "fps": MODULE.FPS,
            "start": {
                "frames": image_batch(30), "audio": audio_value(30 / 24),
                "overlap": start,
            } if start else None,
            "end": {
                "frames": image_batch(24), "audio": audio_value(1.0, offset=500000),
                "overlap": end,
            } if end else None,
        }

    def test_trims_matching_picture_and_audio_and_removes_overhang(self):
        generated = image_batch(100)
        waveform = torch.zeros((1, 2, 100000 + 17))
        result = MODULE.SkebaH3AVConnectorFinalizeTest.execute(
            generated_images=generated,
            generated_audio={"waveform": waveform, "sample_rate": 24000},
            connector_bundle=self.connector_bundle(),
        )
        self.assertEqual(result[0].shape[0], 73)
        self.assertEqual(result[1]["waveform"].shape[-1], 73000)
        self.assertEqual(result[2]["bridge_frames"], 73)

    def test_small_h3_audio_grid_shortfall_is_edge_padded(self):
        generated = image_batch(100)
        sample_rate = 32000
        exact_full_duration = int(round(100 / 24 * sample_rate))
        waveform = torch.arange(
            exact_full_duration - 266, dtype=torch.float32
        ).reshape(1, 1, -1)
        result = MODULE.SkebaH3AVConnectorFinalizeTest.execute(
            generated_images=generated,
            generated_audio={"waveform": waveform, "sample_rate": sample_rate},
            connector_bundle=self.connector_bundle(),
        )

        wanted = int(round(73 / 24 * sample_rate))
        output = result[1]["waveform"]
        self.assertEqual(output.shape[-1], wanted)
        self.assertTrue(torch.equal(output[..., -266:], output[..., -1:].expand(1, 1, 266)))
        self.assertIn("edge-padded 266", result[3])

    def test_audio_shorter_than_one_h3_grid_step_is_still_rejected(self):
        generated = image_batch(100)
        sample_rate = 32000
        exact_full_duration = int(round(100 / 24 * sample_rate))
        waveform = torch.zeros((1, 2, exact_full_duration - 801))
        with self.assertRaisesRegex(ValueError, "grid tolerance is 800"):
            MODULE.SkebaH3AVConnectorFinalizeTest.execute(
                generated_images=generated,
                generated_audio={"waveform": waveform, "sample_rate": sample_rate},
                connector_bundle=self.connector_bundle(),
            )

    def test_bypassed_bundle_returns_generated_media_unchanged(self):
        images = image_batch(5)
        audio = audio_value(5 / 24)
        bundle = {
            "version": MODULE.BUNDLE_VERSION,
            "bypass": True,
            "fps": MODULE.FPS,
            "start": None,
            "end": None,
        }
        result = MODULE.SkebaH3AVConnectorFinalizeTest.execute(images, bundle, audio)
        self.assertTrue(torch.equal(result[0], images))
        self.assertTrue(torch.equal(result[1]["waveform"], audio["waveform"]))


class H3AVConnectorAssembleTests(unittest.TestCase):
    def test_assembly_preserves_endpoints_and_smooths_only_bridge_edges(self):
        start_frames = torch.ones((3, 2, 3, 3))
        bridge_frames = torch.full((4, 2, 3, 3), 2.0)
        end_frames = torch.full((2, 2, 3, 3), 3.0)
        start_audio = {"waveform": torch.ones((1, 2, 3000)), "sample_rate": 24000}
        bridge_audio = {"waveform": torch.full((1, 2, 4000), 2.0), "sample_rate": 24000}
        end_audio = {"waveform": torch.full((1, 2, 2000), 3.0), "sample_rate": 24000}
        seam = {
            "version": MODULE.BUNDLE_VERSION,
            "fps": MODULE.FPS,
            "start": {"frames": start_frames, "audio": start_audio, "overlap": 22},
            "end": {"frames": end_frames, "audio": end_audio, "overlap": 22},
        }
        result = MODULE.SkebaH3AVConnectorAssembleTest.execute(
            bridge_images=bridge_frames,
            bridge_audio=bridge_audio,
            seam_bundle=seam,
            seam_ms=40.0,
        )
        self.assertEqual(result[0].shape[0], 9)
        waveform = result[1]["waveform"]
        self.assertEqual(waveform.shape[-1], 9000)
        self.assertTrue(torch.equal(waveform[..., :3000], start_audio["waveform"]))
        self.assertTrue(torch.equal(waveform[..., -2000:], end_audio["waveform"]))
        self.assertEqual(float(waveform[0, 0, 3000]), 1.0)
        self.assertEqual(float(waveform[0, 0, 6999]), 3.0)
        self.assertEqual(result[2], 24.0)

    def test_missing_audio_segment_becomes_duration_matched_silence(self):
        frames = image_batch(2)
        seam = {
            "version": MODULE.BUNDLE_VERSION,
            "fps": MODULE.FPS,
            "start": {"frames": frames, "audio": None, "overlap": 5},
            "end": None,
        }
        bridge_audio = {
            "waveform": torch.ones((1, 1, 2000)), "sample_rate": 24000
        }
        result = MODULE.SkebaH3AVConnectorAssembleTest.execute(
            bridge_images=frames,
            bridge_audio=bridge_audio,
            seam_bundle=seam,
            seam_ms=0,
        )
        self.assertEqual(result[1]["waveform"].shape[-1], 4000)
        self.assertTrue(torch.equal(result[1]["waveform"][..., :2000], torch.zeros((1, 1, 2000))))

    def test_silent_connector_returns_no_audio(self):
        frames = image_batch(2)
        seam = {
            "version": MODULE.BUNDLE_VERSION,
            "fps": MODULE.FPS,
            "start": None,
            "end": None,
        }
        result = MODULE.SkebaH3AVConnectorAssembleTest.execute(
            bridge_images=frames, seam_bundle=seam
        )
        self.assertIsNone(result[1])

    def test_endpoint_audio_is_resampled_and_channel_matched_to_bridge(self):
        frames = image_batch(2)
        start_audio = {
            "waveform": torch.ones((1, 1, 1000)), "sample_rate": 12000
        }
        seam = {
            "version": MODULE.BUNDLE_VERSION,
            "fps": MODULE.FPS,
            "start": {"frames": frames, "audio": start_audio, "overlap": 5},
            "end": None,
        }
        bridge_audio = {
            "waveform": torch.ones((1, 2, 2000)), "sample_rate": 24000
        }
        with mock.patch.object(
            MODULE,
            "_resample_audio",
            side_effect=lambda waveform, old, new: waveform.repeat_interleave(2, dim=-1),
        ) as resample:
            result = MODULE.SkebaH3AVConnectorAssembleTest.execute(
                bridge_images=frames,
                bridge_audio=bridge_audio,
                seam_bundle=seam,
                seam_ms=0,
            )
        resample.assert_called_once()
        self.assertEqual(result[1]["waveform"].shape, (1, 2, 4000))

    def test_mismatched_endpoint_dimensions_are_center_cropped_by_default(self):
        bridge = image_batch(2)
        seam = {
            "version": MODULE.BUNDLE_VERSION,
            "fps": MODULE.FPS,
            "start": {
                "frames": image_batch(2, height=4, width=3),
                "audio": None,
                "overlap": 5,
            },
            "end": None,
        }
        result = MODULE.SkebaH3AVConnectorAssembleTest.execute(
            bridge_images=bridge, seam_bundle=seam
        )
        self.assertEqual(tuple(result[0].shape), (4, 2, 3, 3))
        self.assertIn("resized source via center_crop", result[3])

    def test_mismatched_endpoint_dimensions_can_remain_strict(self):
        bridge = image_batch(2)
        seam = {
            "version": MODULE.BUNDLE_VERSION,
            "fps": MODULE.FPS,
            "start": {
                "frames": image_batch(2, height=4, width=3),
                "audio": None,
                "overlap": 5,
            },
            "end": None,
        }
        with self.assertRaisesRegex(ValueError, "do not match bridge"):
            MODULE.SkebaH3AVConnectorAssembleTest.execute(
                bridge_images=bridge, seam_bundle=seam,
                endpoint_resize="error",
            )


if __name__ == "__main__":
    unittest.main()
