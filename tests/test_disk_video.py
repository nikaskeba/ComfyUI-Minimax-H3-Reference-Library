"""Small CPU/FFmpeg integration tests, without loading models or the extension server."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent.parent))
spec = importlib.util.spec_from_file_location("disk_video_test_module", ROOT / "disk_video.py")
disk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(disk)

import av
import torch
from comfy_api.latest import InputImpl, Types


def video(frames=24, width=64, height=48, fps=24, audio=True):
    images = torch.zeros(frames, height, width, 3)
    images[-6:, ..., 0] = 1
    waveform = torch.sin(torch.arange(round(frames / fps * 44100)) * (440 * 2 * torch.pi / 44100)) * .1
    return InputImpl.VideoFromComponents(Types.VideoComponents(
        images=images, frame_rate=fps,
        audio={"waveform": waveform[None, None], "sample_rate": 44100} if audio else None))


def inspect(path):
    with av.open(str(path)) as container:
        count = sum(1 for _ in container.decode(video=0))
    with av.open(str(path)) as container:
        audio = container.streams.audio[0]
        samples = sum(frame.samples for frame in container.decode(audio=0))
        return count, samples / audio.rate


class DiskVideoTests(unittest.TestCase):
    def test_live_playlist_registration_and_media_access(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(disk.folder_paths, "get_output_directory", return_value=directory), \
                patch.object(disk.folder_paths, "get_user_directory", return_value=str(Path(directory) / "user")):
            saver = disk.SaveClipToFile()
            first = saver.save(video(), live_playlist=True, prompt="First prompt")
            token = first["ui"]["skeba_playlist"][0]
            clip = first["result"][0]
            second = saver.save(video(), accumulation={"accum": [clip]}, live_playlist=True, prompt="Second prompt")
            self.assertEqual(second["ui"]["skeba_playlist"], [token])
            root, manifest = disk.playlist_manifest(token)
            self.assertEqual(len(manifest["clips"]), 2)
            self.assertEqual(manifest["clips"][1]["prompt"], "Second prompt")
            self.assertEqual(disk.playlist_media(token, manifest["clips"][0]["clip_id"]), Path(clip.get_stream_source()).resolve())
            self.assertIn(token, disk.playlist_projects())
            with self.assertRaises(FileNotFoundError):
                disk.playlist_media(token, "../../secret")
            with self.assertRaises(FileNotFoundError):
                disk.playlist_manifest("unknown")
            manifest["clips"][0]["filename"] = "../outside.mp4"
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                disk.playlist_media(token, manifest["clips"][0]["clip_id"])

    def test_prompt_manifest_and_temporary_concat(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(disk.folder_paths, "get_output_directory", return_value=directory):
            saver = disk.SaveClipToFile()
            prompt = '[s=5]\n[Shot 1] A guest says "Hello!"\nSecond line.'
            first, = saver.save(video(frames=17), prompt=prompt)
            bundle = Path(first.get_stream_source()).parent
            manifest = json.loads((bundle / "manifest.json").read_text())
            self.assertEqual(manifest["clips"][0]["prompt"], prompt)
            self.assertEqual(manifest["clips"][0]["frame_count"], 17)
            self.assertAlmostEqual(manifest["clips"][0]["duration_seconds"], 17 / 24)
            second, = saver.save(video(), accumulation={"accum": [first]})
            combined, _ = disk.combine_disk_clips([first, second], starting_video=video())
            manifest = json.loads((bundle / "manifest.json").read_text())
            self.assertEqual(len(manifest["clips"]), 2)
            self.assertEqual(manifest["clips"][1]["prompt"], "")
            self.assertEqual(Path(manifest["clips"][1]["previous_file"]), Path(first.get_stream_source()).resolve())
            final = manifest["combined_videos"][0]
            self.assertEqual(final["filename"], Path(combined.get_stream_source()).name)
            self.assertEqual([c["role"] for c in final["clips"]], ["starting", "generated", "generated"])
            self.assertFalse(list(bundle.glob("concat*.txt")))

    def test_preview_returns_ui_and_preserves_disk_clip(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(disk.folder_paths, "get_output_directory", return_value=directory), \
                patch.object(disk.folder_paths, "get_temp_directory", return_value=str(Path(directory) / "temp")):
            result = disk.SaveClipToFile().save(video(), preview_clip=True)
            self.assertIsInstance(result["result"][0], disk.DiskClip)
            self.assertTrue(result["result"][0].get_stream_source().endswith(".mp4"))
            descriptor = result["ui"]["images"][0]
            preview = Path(directory) / "temp" / descriptor["subfolder"] / descriptor["filename"]
            self.assertEqual(descriptor["type"], "temp")
            frames, seconds = inspect(preview)
            self.assertEqual(frames, 24)
            self.assertLess(abs(seconds - 1), .025)

    def test_project_bundle_paths(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(disk.folder_paths, "get_output_directory", return_value=directory):
            saver = disk.SaveClipToFile()
            first, = saver.save(video(), output_folder="Videos", project_name="Episode's test")
            bundle = Path(first.get_stream_source()).parent
            self.assertEqual(bundle.parent, Path(directory) / "Videos" / "Episode's test")
            second, = saver.save(video(), accumulation={"accum": [first]}, output_folder="Videos", project_name="Episode's test")
            self.assertEqual(Path(second.get_stream_source()).parent, bundle)
            combined, _ = disk.combine_disk_clips([first, second])
            self.assertEqual(Path(combined.get_stream_source()).parent, bundle)
            self.assertEqual(inspect(combined.get_stream_source())[0], 48)
            other, = saver.save(video(), output_folder=str(Path(directory) / "absolute"), project_name="Project")
            self.assertEqual(Path(other.get_stream_source()).parent.parent, Path(directory) / "absolute" / "Project")
            with self.assertRaises(ValueError):
                saver.save(video(), project_name="../outside")

    def test_save_accumulate_combine_and_tail(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(disk.folder_paths, "get_output_directory", return_value=directory):
            saver = disk.SaveClipToFile()
            first, = saver.save(video())
            second, = saver.save(video(audio=False), accumulation={"accum": [first]})
            self.assertEqual(Path(first.get_stream_source()).parent, Path(second.get_stream_source()).parent)
            self.assertEqual(inspect(first.get_stream_source())[0], 24)
            self.assertLess(abs(inspect(first.get_stream_source())[1] - 1.0), .025)
            tail = first.seam_frames(6)
            self.assertEqual(tuple(tail.shape), (6, 48, 64, 3))
            self.assertGreater(tail[..., 0].mean(), .9)
            # Concatenation must never decode clips through get_components.
            with patch.object(disk.DiskClip, "get_components", side_effect=AssertionError("decoded during concat")):
                combined, count = disk.combine_disk_clips([first, second])
            self.assertEqual(count, 2)
            frames, seconds = inspect(combined.get_stream_source())
            self.assertEqual(frames, 48)
            self.assertLess(abs(seconds - 2), .025)  # final AAC packet padding

    def test_bookends_resize_fps_and_silence(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(disk.folder_paths, "get_output_directory", return_value=directory):
            clip, = disk.SaveClipToFile().save(video())
            result, count = disk.combine_disk_clips([clip], video(12, 96, 64, 12, False), video(30, 48, 64, 30))
            self.assertEqual(count, 3)
            self.assertEqual(disk._geometry(result.get_stream_source())[:2], (64, 48))
            frames, seconds = inspect(result.get_stream_source())
            self.assertEqual(frames, 72)
            self.assertLess(abs(seconds - 3), .025)

    def test_mismatched_clips_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(disk.folder_paths, "get_output_directory", return_value=directory):
            saver = disk.SaveClipToFile()
            first, = saver.save(video())
            second, = saver.save(video(width=96))
            with self.assertRaisesRegex(ValueError, "matching dimensions"):
                disk.combine_disk_clips([first, second])

    def test_fractional_durations_and_final_save(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(disk.folder_paths, "get_output_directory", return_value=directory):
            clips = []
            saver = disk.SaveClipToFile()
            for _ in range(6):
                clip, = saver.save(video(frames=17), accumulation={"accum": clips})
                clips.append(clip)
            result, _ = disk.combine_disk_clips(clips)
            destination = Path(directory) / "final.mp4"
            result.save_to(str(destination), format=Types.VideoContainer.MP4, codec=Types.VideoCodec.H264)
            frames, seconds = inspect(destination)
            self.assertEqual(frames, 102)
            self.assertLess(abs(seconds - 102 / 24), .025)


if __name__ == "__main__":
    unittest.main()
