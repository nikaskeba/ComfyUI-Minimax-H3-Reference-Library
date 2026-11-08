"""CPU integration check for the installed VHS chunk loader and final audio mux."""
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.argv = ["test", "--cpu"]
import comfy.options
comfy.options.enable_args_parsing()
import folder_paths
import server
import torch

server.PromptServer.instance = types.SimpleNamespace(prompt_queue=None)
spec = importlib.util.spec_from_file_location("chunk_plan", Path(__file__).parents[1] / "video_chunk_plan.py")
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)
package = types.ModuleType("vhs_test")
package.__path__ = [str(ROOT / "custom_nodes/comfyui-videohelpersuite")]
sys.modules["vhs_test"] = package
vhs = importlib.import_module("vhs_test.videohelpersuite.nodes")
load = importlib.import_module("vhs_test.videohelpersuite.load_video_nodes")

with tempfile.TemporaryDirectory() as temp:
    source = Path(temp) / "source.mp4"
    output = Path(temp) / "output"
    output.mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=32x32:rate=24:duration=120",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=120",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(source)], check=True)
    with patch.object(folder_paths, "get_input_directory", return_value=temp):
        path, frames, fps, report = plan.SkebaVideoChunkPlan().plan("source.mp4", 30)
        assert frames == 720 and fps == 24, report
        try:
            plan.SkebaVideoChunkPlan().plan("../outside.mp4", 30)
        except ValueError:
            pass
        else:
            raise AssertionError("Path escape accepted")
    # Test an exact four-chunk input and an uneven last chunk.
    for batch_frames, expected_counts in [(frames, [720] * 4), (1000, [1000, 1000, 880])]:
        manager = vhs.BatchManager(batch_frames)
        manager.unique_id = "batch"
        counts, requeues = [], []
        with patch.object(folder_paths, "get_output_directory", return_value=str(output)), patch.object(vhs, "requeue_workflow", side_effect=requeues.append):
            for iteration in range(10):
                images, count, audio, info = load.load_video(
                    video=path, force_rate=0, custom_width=0, custom_height=0, frame_load_cap=0,
                    skip_first_frames=0, select_every_nth=1, meta_batch=manager, unique_id="load", format="None")
                counts.append(count)
                # Only GPU effects are substituted; match RTX's actual frame-count contract.
                interpolated = torch.repeat_interleave(images, 2, dim=0)[:-1]
                fixed = plan.SkebaRTXChunkTiming().complete(interpolated, count, 2)[0]
                assert len(fixed) == count * 2
                result = vhs.VideoCombine().combine_video(
                    images=fixed, frame_rate=48, loop_count=0, filename_prefix=f"final_{batch_frames}",
                    format="video/h264-mp4", pingpong=False, save_output=True, audio=audio,
                    unique_id="combine", meta_batch=manager,
                    extra_pnginfo={"workflow": {"extra": {"VHS_KeepIntermediate": False, "VHS_MetadataImage": False}}},
                    pix_fmt="yuv420p", crf=23, save_metadata=False, trim_to_audio=False)
                del images, interpolated, fixed
                if not result.get("ui", {}).get("unfinished_batch"):
                    break
            assert counts == expected_counts, counts
            files = list(output.glob(f"final_{batch_frames}*"))
            assert len(files) == 1, files
            metadata = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(files[0])]))
            video = next(s for s in metadata["streams"] if s["codec_type"] == "video")
            sound = next(s for s in metadata["streams"] if s["codec_type"] == "audio")
            assert int(video["nb_frames"]) == 5760, video
            assert abs(float(video["duration"]) - 120) < .001
            assert abs(float(sound["duration"]) - 120) < .05
            assert [r[1] for r in requeues] == [True] * (len(counts) - 1) + [False], requeues
            print(f"PASS {counts}: 5760 frames, 120s audio/video, one final file, correct requeue requests.")
    for count in (1, 2, 7):
        for multiplier in (1, 2, 3):
            images = torch.zeros(((count - 1) * multiplier + 1, 2, 2, 3))
            fixed = plan.SkebaRTXChunkTiming().complete(images, count, multiplier)[0]
            assert len(fixed) == count * multiplier
print("PASS single-frame tails and multipliers 1/2/3.")
