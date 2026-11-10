"""CPU checks and a small local benchmark for Skeba Video Effects."""
import importlib
from pathlib import Path
import statistics
import sys
import time
import types

import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.argv = ["check", "--cpu"]
import comfy.options
comfy.options.enable_args_parsing()

package = types.ModuleType("skeba_fx_test")
package.__path__ = [str(Path(__file__).parents[1])]
sys.modules[package.__name__] = package
effects = importlib.import_module("skeba_fx_test.video_effects")
node = effects.SkebaVideoEffects
torch.set_num_threads(4)
node.define_schema()
tape_options = {name: spec[1].get("default", spec[0][0] if isinstance(spec[0], list) else None)
                for name, spec in effects.TapeEngine.INPUT_TYPES()["required"].items()
                if name not in ("image", "format", "seed")}
tape_options["osd_enabled"] = False
profiles = [{"effect": name, **tape_options} for name in ("VHS", "BetaMax", "LaserDisc")]
profiles += [
    dict(effect="Film Grain", grain=.25, grain_size=1.5, color_grain=.15),
    dict(effect="MiniDV", compression=.35, chroma_loss=.65, sensor_noise=.08, interlace=.15),
    dict(effect="35mm to 1990s TV", grain=.2, softness=.4, color_bleed=.35, scanlines=.2, warmth=.2, flicker=.08),
]
image = torch.rand(3, 48, 64, 4)
original = image.clone()
for profile in profiles:
    for speed in ("Fast", "Balanced", "Full Resolution"):
        result = node.execute(image, profile, speed, seed=42)[0]
        assert result.shape == image.shape and result.device == image.device
        assert torch.isfinite(result).all() and result.min() >= 0 and result.max() <= 1
        torch.testing.assert_close(result[..., 3], image[..., 3])
        torch.testing.assert_close(image, original)
        torch.testing.assert_close(result, node.execute(image, profile, speed, seed=42)[0])
    if profile["effect"] in ("VHS", "BetaMax", "LaserDisc"):
        expected = effects.TapeEngine().apply(image[..., :3], profile["effect"].lower(), seed=42, **tape_options)[0]
        torch.testing.assert_close(result[..., :3], expected)
    else:
        chunks = torch.cat([node.execute(image[:1], profile, seed=42)[0],
                            node.execute(image[1:], profile, seed=42, frame_offset=1)[0]])
        torch.testing.assert_close(result, chunks)
    print("PASS", profile["effect"])

for shape in ((1, 1, 1, 3), (1, 33, 65, 3)):
    for profile in profiles[3:]:
        assert node.execute(torch.rand(shape), profile)[0].shape == shape

image = torch.rand(4, 720, 1280, 3)
for profile in (profiles[0], profiles[3], profiles[5]):
    timings = {}
    for speed in ("Fast", "Full Resolution"):
        node.execute(image[:1], profile, speed)
        elapsed = []
        for _ in range(3):
            start = time.perf_counter()
            result = node.execute(image, profile, speed)[0]
            assert result.shape == image.shape
            elapsed.append(time.perf_counter() - start)
        timings[speed] = statistics.median(elapsed)
    print(profile["effect"], timings, "speedup", round(timings["Full Resolution"] / timings["Fast"], 2))
