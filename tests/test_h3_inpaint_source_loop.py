import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import wave
from unittest.mock import patch
import sys
import types

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("h3_inpaint_source_loop_test", ROOT / "h3_inpaint_source_loop.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WindowPlanTests(unittest.TestCase):
    def test_short_tail_removes_only_out_of_range_timed_shots(self):
        prompt = ("[s=15]\n\ndetailed_description:\n"
                  "[Shot 1: 0s] Establish.\n\n"
                  "[Shot 2: 4.0s] Speak.\n\n"
                  "[Shot 3: 12.0s] Too late.\n\n"
                  "overall_soundscape:\nRoom tone.\n\n"
                  "non_diegetic_music:\nN/A")
        fitted = MODULE._fit_duration_tag(prompt, 226)
        self.assertIn("[s=9.416667]", fitted)
        self.assertIn("[Shot 2: 4.0s]", fitted)
        self.assertNotIn("[Shot 3: 12.0s]", fitted)
        self.assertIn("overall_soundscape:\nRoom tone.", fitted)
        old = "[Shot 1] Establish.\n[Shot 2] At 00:12.000, Too late.\nnon_diegetic_music:\nN/A"
        self.assertNotIn("[Shot 2]", MODULE._fit_duration_tag(old, 226))

    def test_batch_fit_shortens_final_prompt_and_omits_exhausted_prompts(self):
        prompts = ["[s=15] one", "[s=15] two", "[s=15] three"]
        fitted, plans = MODULE.fit_prompt_batch(prompts, 620, 0, 15, 22)
        self.assertEqual(len(fitted), 2)
        self.assertEqual(plans[-1]["source_end_frame"], 617)
        self.assertEqual(plans[-1]["head_trim"], 22)
        self.assertIn("[s=10.625]", fitted[-1])
        self.assertEqual(fitted[0], prompts[0])
        ten_second_tail, tail_plans = MODULE.fit_prompt_batch(
            ["[s=15] one"], 240, 0, 15, 22)
        self.assertEqual(tail_plans[0]["render_frames"], 226)
        self.assertIn("[s=9.416667]", ten_second_tail[0])
        with self.assertRaisesRegex(ValueError, "Fewer than five"):
            MODULE.fit_prompt_batch(prompts, 4, 0, 15, 22)

    def test_three_prompts_advance_by_saved_frames(self):
        plans = MODULE.plan_windows(["[s=15] one", "[s=15] two", "[s=15] three"],
                                    104, 12, 22)
        self.assertEqual([p["render_frames"] for p in plans], [362, 379, 379])
        self.assertEqual([p["head_trim"] for p in plans], [0, 22, 22])
        self.assertEqual([p["appended_frames"] for p in plans], [362, 357, 357])
        self.assertEqual([p["source_start_frame"] for p in plans], [104, 444, 801])
        for before, after in zip(plans, plans[1:]):
            self.assertEqual(before["delivered_end_frame"], after["delivered_start_frame"])
            self.assertEqual(after["source_start_frame"] + after["head_trim"],
                             after["delivered_start_frame"])
        self.assertEqual(plans[-1]["delivered_end_frame"] - 104,
                         sum(p["appended_frames"] for p in plans))

    def test_prompt_override_default_scene_reset_and_settling(self):
        plans = MODULE.plan_windows(["[s=12] one", "[new_location] [s=5] two", "three"],
                                    0, 15, 22, settling_frames=10)
        self.assertEqual([p["requested_frames"] for p in plans], [288, 120, 360])
        self.assertEqual([p["head_trim"] for p in plans], [0, 0, 39])
        self.assertEqual(plans[1]["source_start_frame"], plans[0]["delivered_end_frame"])
        self.assertEqual(plans[2]["source_start_frame"] + 39,
                         plans[1]["delivered_end_frame"])

    def test_invalid_duration_and_bypass_are_actionable(self):
        with self.assertRaisesRegex(ValueError, "positive finite"):
            MODULE.plan_windows(["[s=0]"], 0, 15, 22)
        with self.assertRaisesRegex(ValueError, "bypass disagrees"):
            MODULE.plan_windows(["one", "two"], 0, 15, 22,
                                current_bypass=True, current_index=1)

    def test_validator_checks_saved_length_and_audio(self):
        node = MODULE.SkebaH3InpaintWindowValidate()
        frames = torch.zeros((22, 2, 2, 3))
        audio = {"waveform": torch.ones((1, 2, 11000)), "sample_rate": 12000}
        out_frames, out_audio, _ = node.validate(frames, audio, 5, 5, 22)
        self.assertIs(out_frames, frames)
        self.assertEqual(out_audio["waveform"].shape[-1], 11000)
        with self.assertRaisesRegex(ValueError, "Motion Context returned"):
            node.validate(frames, audio, 0, 5, 22)
        with self.assertRaisesRegex(ValueError, "expected 23 saved frames"):
            node.validate(frames, audio, 5, 5, 23)


class FrameWindowLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.root = Path(cls.folder.name)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def _make_video(self, fps):
        path = self.root / f"numbered_{fps}.mkv"
        if path.exists():
            return path
        count = fps * 6
        frames = np.zeros((count, 16, 24, 3), dtype=np.uint8)
        frames[:, :, :, 0] = np.arange(count, dtype=np.uint8)[:, None, None]
        frames[:, :, :, 1] = (np.arange(count) // 256).astype(np.uint8)[:, None, None]
        samples = np.zeros(44100 * 6, dtype=np.int16)
        for second in range(6):
            samples[second * 44100:second * 44100 + 100] = 16000
        wav_path = self.root / f"pulses_{fps}.wav"
        with wave.open(str(wav_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            wav.writeframes(samples.tobytes())
        cmd = [MODULE._ffmpeg_executable(), "-v", "error", "-y", "-f", "rawvideo",
               "-pix_fmt", "rgb24", "-s", "24x16", "-r", str(fps), "-i", "pipe:0",
               "-i", str(wav_path), "-c:v", "ffv1", "-c:a", "pcm_s16le", str(path)]
        subprocess.run(cmd, input=frames.tobytes(), check=True, capture_output=True)
        return path

    def test_frame_index_windows_match_full_normalized_timeline(self):
        for fps in (24, 30):
            with self.subTest(fps=fps):
                path = self._make_video(fps)
                full = MODULE._decode_window(str(path), 0, 124, 24, 16)
                first = MODULE._decode_window(str(path), 12, 22, 24, 16)
                second = MODULE._decode_window(str(path), 34, 22, 24, 16)
                self.assertTrue(torch.equal(first, full[12:34]))
                self.assertTrue(torch.equal(second, full[34:56]))
                audio_full = MODULE._decode_audio_window(str(path), 0, 124)
                audio_part = MODULE._decode_audio_window(str(path), 12, 22)
                sample_offset = round(12 * 44100 / 24)
                self.assertTrue(torch.equal(audio_part["waveform"],
                                            audio_full["waveform"][..., sample_offset:sample_offset + 22 * 44100 // 24]))

    def test_short_source_fails_before_generation(self):
        path = self._make_video(24)
        with self.assertRaisesRegex(ValueError, "only .* required normalized"):
            MODULE._decode_window(str(path), 140, 22, 24, 16)

    def test_exact_normalized_count_and_short_audio_silence(self):
        for fps in (24, 30):
            path = self._make_video(fps)
            stat = path.stat()
            self.assertEqual(MODULE._normalized_video_frame_count(
                str(path), stat.st_size, stat.st_mtime_ns), 144)
        short = self.root / "short_audio.wav"
        with wave.open(str(short), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            wav.writeframes(np.ones(44100 * 2, dtype=np.int16).tobytes())
        audio = MODULE._decode_audio_window(str(short), 0, 124)
        self.assertEqual(audio["waveform"].shape[-1], round(124 * 44100 / 24))
        self.assertGreater(float(audio["waveform"][..., :44100].abs().mean()), 0)
        self.assertEqual(float(audio["waveform"][..., 2 * 44100:].abs().max()), 0)
        self.assertGreater(audio["padded_silence_seconds"], 3)
        ended = MODULE._decode_audio_window(str(short), 124, 22)
        self.assertEqual(float(ended["waveform"].abs().max()), 0)

    def test_batch_fit_uses_selected_video_and_reports_omitted_prompts(self):
        path = self._make_video(30)
        fake_paths = types.SimpleNamespace(
            get_input_directory=lambda: str(self.root),
            get_annotated_filepath=lambda name: str(self.root / name),
        )
        with patch.dict(sys.modules, {"folder_paths": fake_paths}):
            prompts, count, video, start, status = MODULE.SkebaH3InpaintBatchFit().fit(
                ["[s=15] first", "[s=15] second"], path.name, 0, 15, 22, 0)
        self.assertEqual(count, 1)
        self.assertEqual(video, path.name)
        self.assertEqual(start, 0)
        self.assertIn("1 prompt(s) beyond the source end omitted", status)
        self.assertIn("[s=5.875]", prompts[0])

    def test_fixed_reference_and_audio_source_modes(self):
        path = self._make_video(30)
        custom = self.root / "custom.wav"
        with wave.open(str(custom), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            wav.writeframes(np.ones(44100 * 6, dtype=np.int16).tobytes())
        fake_paths = types.SimpleNamespace(
            get_input_directory=lambda: str(self.root),
            get_annotated_filepath=lambda name: str(self.root / name),
        )
        node = MODULE.SkebaH3InpaintSourceWindow()
        with patch.dict(sys.modules, {"folder_paths": fake_paths}):
            frames, audio, _, reference, mode, video_mode = node.load(
                path.name, 24, 22, reference_frame=50)
            self.assertEqual(frames.shape[0], 22)
            self.assertTrue(torch.equal(reference, MODULE._decode_window(str(path), 50, 1, 24, 16)))
            self.assertEqual(mode, "preserve source audio")
            self.assertEqual(video_mode, "source video inpaint")
            self.assertGreater(float(audio["waveform"].abs().max()), 0)
            _, custom_audio, status, _, mode, _ = node.load(
                path.name, 46, 22, video_origin_frame=24, reference_frame=50,
                audio_source="custom audio", custom_audio=custom.name,
                custom_audio_start_frame=48)
            self.assertEqual(mode, "preserve source audio")
            self.assertIn("custom audio frames 70–91", status)
            self.assertGreater(float(custom_audio["waveform"].abs().mean()), 0)
            self.assertTrue(torch.equal(
                custom_audio["waveform"],
                MODULE._decode_audio_window(str(custom), 70, 22)["waveform"],
            ))
            _, generated_audio, _, _, mode, _ = node.load(
                path.name, 24, 22, reference_frame=50,
                audio_source="generate new audio")
            self.assertEqual(mode, "generate audio")
            self.assertEqual(float(generated_audio["waveform"].abs().max()), 0)
            with self.assertRaisesRegex(ValueError, "before frame zero"):
                node.load(path.name, 12, 22, video_origin_frame=24,
                          audio_source="custom audio", custom_audio=custom.name)
            blank, audio_only, _, _, _, video_mode = node.load(
                "(no source video)", 24, 22, video_origin_frame=24,
                audio_source="custom audio", custom_audio=custom.name,
                video_generation_mode="audio drives video")
            self.assertEqual(tuple(blank.shape), (22, 64, 64, 3))
            self.assertGreater(float(audio_only["waveform"].abs().mean()), 0)
            self.assertEqual(video_mode, "audio drives video")
            with self.assertRaisesRegex(ValueError, "only in audio-drives-video mode"):
                node.load("(no source video)", 24, 22,
                          audio_source="video audio")


class WorkflowWiringTests(unittest.TestCase):
    def test_loop_uses_planned_window_and_validates_append(self):
        graph = json.loads((ROOT / "example/Video-Audio-Inpaint-Oct16.json")
                           .read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in graph["nodes"]}
        links = {link[0]: link for link in graph["links"]}
        planner = next(node for node in nodes.values() if node["type"] == "SkebaH3InpaintWindowPlan")
        fitter = next(node for node in nodes.values() if node["type"] == "SkebaH3InpaintBatchFit")
        loader = next(node for node in nodes.values() if node["type"] == "SkebaH3InpaintSourceWindow")
        checker = next(node for node in nodes.values() if node["type"] == "SkebaH3InpaintWindowValidate")
        source_of = lambda node, name: links[next(i["link"] for i in node["inputs"] if i["name"] == name)][1]
        self.assertEqual(source_of(fitter, "prompt_batch"), 258)
        self.assertEqual(source_of(fitter, "settling_frames"), 1369)
        self.assertEqual(source_of(nodes[912], "settling_frames"), 1369)
        self.assertNotEqual(source_of(fitter, "settling_frames"), 920)
        self.assertEqual(source_of(nodes[257], "initial_value1"), fitter["id"])
        self.assertEqual(source_of(nodes[257], "remaining"), fitter["id"])
        self.assertEqual(source_of(planner, "prompt_batch"), fitter["id"])
        self.assertEqual(source_of(planner, "start_frame"), fitter["id"])
        self.assertEqual(source_of(planner, "index"), 267)
        self.assertEqual(source_of(loader, "video"), fitter["id"])
        self.assertEqual(source_of(loader, "start_frame"), planner["id"])
        self.assertEqual(source_of(loader, "frame_count"), planner["id"])
        self.assertEqual(source_of(loader, "video_origin_frame"), planner["id"])
        self.assertEqual(source_of(nodes[1285], "value"), loader["id"])
        self.assertEqual(source_of(nodes[1283], "value"), loader["id"])
        self.assertEqual(source_of(nodes[546], "length"), 1180)
        self.assertEqual(source_of(checker, "actual_head_trim"), 263)
        self.assertEqual(source_of(nodes[336], "images"), checker["id"])
        self.assertEqual(source_of(nodes[295], "audio"), checker["id"])
        self.assertEqual(source_of(nodes[1292], "source_video"), 1167)
        self.assertEqual(source_of(nodes[1312], "frames"), loader["id"])
        self.assertEqual(source_of(nodes[1170], "audio_mode"), loader["id"])
        self.assertEqual(source_of(nodes[1292], "generated_video"), 298)
        self.assertEqual(source_of(nodes[300], "latent_image"), 1358)
        for link in graph["links"]:
            lid, src, src_slot, dst, dst_slot, _ = link
            self.assertIn(lid, nodes[src]["outputs"][src_slot]["links"])
            self.assertEqual(nodes[dst]["inputs"][dst_slot]["link"], lid)


if __name__ == "__main__":
    unittest.main()
