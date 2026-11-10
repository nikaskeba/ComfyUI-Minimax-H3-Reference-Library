"""CPU regression checks for source advancement, edit ranges and saved wiring."""
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT.parents[1]), str(ROOT / "tests")]
sys.argv = ["check", "--cpu"]
import comfy.options
comfy.options.enable_args_parsing()

package = types.ModuleType("mixing_test")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
mix = importlib.import_module("mixing_test.av_mixing")
import test_h3_audio_refine
mask = test_h3_audio_refine.MODULE

mix.SkebaH3MixingSource.define_schema()
mix.SkebaH3MixingTrim.define_schema()
assert mix.mixing_window("[s=2] A | [s=3] B", 2, 8, 1, 22) == (50, 72, 22, 48)
assert mix.mixing_window("A | B", 1, 8, 0) == (0, 192, 0, 0)

value = {"samples": mask.comfy.nested_tensor.NestedTensor((torch.zeros(1, 24, 72, 2, 2), torch.zeros(1, 32, 2, 405)))}
out, _ = mask.SkebaH3VideoEditMask().apply(value, edit_ranges="0-1; 3-4", time_offset_seconds=1)
v = out["noise_mask"].tensors[0]
assert not v[:, :, :7].any() and v[:, :, 8:14].all()
assert not v[:, :, 15:28].any() and v[:, :, 29:35].all()
both, _ = mask.SkebaH3AudioEditMask().apply(out, edit_ranges="0-1\n3-4; 20-30", time_offset_seconds=1)
a = both["noise_mask"].tensors[1]
assert both["noise_mask"].tensors[0] is v
assert not a[..., :40].any() and a[..., 40:80].all()
assert not a[..., 80:160].any() and a[..., 160:200].all() and not a[..., 200:].any()
assert mask._h3_video_token_frames(72) == 243
assert mask.edit_intervals("2-999; 500-999", 0, 0, 8) == [(2, 8)]
clamped, _ = mask.SkebaH3AudioEditMask().apply(value, edit_ranges="2-999")
assert not clamped["noise_mask"].tensors[1][..., :80].any()
assert clamped["noise_mask"].tensors[1][..., 80:].all()
clamped, _ = mask.SkebaH3VideoEditMask().apply(value, edit_ranges="2-999")
assert clamped["noise_mask"].tensors[0][:, :, -1].all()

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "source.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=64x48:rate=30:duration=8",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=8",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    with patch.object(mix.folder_paths, "get_input_directory", return_value=directory):
        for index, head, render in [(1, 0, 56), (2, 22, 73)]:
            result = mix.SkebaH3MixingSource.execute("source.mp4", 1, "video audio", "(none)", 0,
                                                   "[s=2] A | [s=2] B", index, 8, render, head)
            images, audio = result[0], result[1]
            assert len(images) == render and result[3] == 48 and result[5] == head / 24
            expected_start = 24 + (index - 1) * 48 - head
            expected = mix._decode_window(str(path), expected_start, render, 64, 48)
            torch.testing.assert_close(images, expected)
            sr = audio["sample_rate"]
            trimmed = mix.SkebaH3MixingTrim.execute(images[head:], {**audio, "waveform": audio["waveform"][..., round(head * sr / 24):]}, 48)
            assert len(trimmed[0]) == 48 and trimmed[1]["waveform"].shape[-1] == 2 * sr
        custom = mix.SkebaH3MixingSource.execute("source.mp4", 1, "custom audio", "source.mp4", 0,
                                               "[s=2] A", 1, 8, 73, 22)
        prefix = round(22 * custom[1]["sample_rate"] / 24)
        assert not custom[1]["waveform"][..., :prefix].any()
        assert custom[1]["waveform"].shape[-1] == round(73 * custom[1]["sample_rate"] / 24)

for path in [ROOT / "example/Audio Video Mixing Nov 9 26.json", ROOT.parents[1] / "user/default/workflows/Audio Video Mixing Nov 9 26.json"]:
    workflow = json.loads(path.read_text(encoding="utf-8"))
    for graph in [workflow] + workflow["definitions"]["subgraphs"]:
        nodes = {n["id"]: n for n in graph["nodes"]}
        for raw in graph["links"]:
            link = raw if isinstance(raw, list) else [raw[k] for k in ("id", "origin_id", "origin_slot", "target_id", "target_slot", "type")]
            lid, source, slot, target, target_slot, _ = link
            if source in nodes:
                assert lid in (nodes[source]["outputs"][slot].get("links") or []), (path, "source", link)
            if target in nodes:
                assert nodes[target]["inputs"][target_slot]["link"] == lid, (path, "target", link)
    nodes = {n["id"]: n for n in workflow["nodes"]}
    if path.parent.name == "example":
        assert nodes[4592]["type"] == "SkebaH3MixingSource"
    masks = next(g for g in workflow["definitions"]["subgraphs"] if g["id"] == nodes[4603]["type"])
    assert [p["name"] for p in masks["inputs"]] == [p["name"] for p in nodes[4603]["inputs"]]

result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(test_h3_audio_refine))
assert result.wasSuccessful()
print("PASS: source decoding, two-prompt advancement, custom audio, exact duration, disjoint edit ranges and both workflow graphs")
