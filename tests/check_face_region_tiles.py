"""Check face strength/noise alignment through both Ultimate Upscale tile paths."""
import importlib.util
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.argv = ["check", "--cpu"]
import comfy.options
comfy.options.enable_args_parsing()
import torch
import comfy.nested_tensor
import comfy.sample
from comfy.ldm.minimax.model import mask_row_values


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / "custom_nodes" / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


face = load("face_region_check", "comfyui-open-h3-face-region/__init__.py")
upscale = load("ultimate_check", "plaguekind-nodes/ComfyUI-H3-UltimateUpscale-LD/nodes.py")
mask = torch.linspace(.2, 1, 107)[:, None, None].expand(107, 78, 104).clone()
part = face._window_mask(mask, (35, 40, 78, 104, 0, 0, 78, 104))
assert part.shape == (40, 78, 104)
assert mask_row_values(part, 40, 78, 104).shape == (40 * 39 * 52,)
torch.testing.assert_close(part, mask[35:75])

# Distinct time and spatial regions reveal incorrect whole-map resizing/cropping.
mask = torch.linspace(.1, 1, 10 * 4 * 4).reshape(10, 4, 4)
noise = face._RegionNoise(42, mask)
video = torch.zeros(1, 24, 3, 8, 8)
audio = torch.zeros(1, 32, 2, 4)
full_window = (4, 3, 8, 8, 0, 0, 8, 8)
full_mask = face._window_mask(mask, full_window)


class Model:
    model_options = {}

    def clone(self):
        result = Model()
        result.model_options = dict(self.model_options)
        return result

    def set_model_unet_function_wrapper(self, wrapper):
        self.wrapper = wrapper


with patch.object(face, "_load", return_value=mask):
    model = face.OpenH3RegionModel().patch(Model(), "test.npy")[0]
window = (4, 3, 8, 8, 2, 4, 4, 4)
received = {}


def apply_model(x, timestep, **conditions):
    received.update(conditions)
    return x


model.wrapper(apply_model, {"input": torch.zeros(2, 10), "timestep": torch.ones(2),
                           "c": {"transformer_options": {"h3_latent_window": window}}})
assert received["denoise_mask"].shape == (2, 1, 3, 4, 4)
torch.testing.assert_close(received["denoise_mask"][0, 0], full_mask[:, 2:6, 4:8])
print("PASS model wrapper forwards the correct tile mask for batched conditioning")

source = comfy.nested_tensor.NestedTensor((video, audio))
raw = comfy.sample.prepare_noise(source, 42)
generated = noise.generate_noise({"samples": source, "h3_latent_window": full_window})
torch.testing.assert_close(generated.tensors[0], raw.tensors[0] * full_mask[None, None])

sp = dict(tile_width=64, tile_height=64, spatial_w_overlap=32, spatial_h_overlap=32,
          fade_width=32, fade_height=32, min_tile_size=32,
          overlap_mode="earlier", overlap_blend="linear")
for process in (upscale.spatial_process_joint, upscale.spatial_process):
    calls = []

    def sample(piece, cond, model, tile_noise, sampler, sigmas, negative, cfg):
        window = piece["h3_latent_window"]
        start, count, height, width, top, left, tile_h, tile_w = window
        assert start == 4 and count == 3
        cropped = face._window_mask(mask, window)
        torch.testing.assert_close(cropped, full_mask[:, top:top + tile_h, left:left + tile_w])
        tiled = tile_noise.generate_noise(piece).tensors[0]
        torch.testing.assert_close(tiled, generated.tensors[0][:, :, :, top:top + tile_h, left:left + tile_w])
        assert cropped.shape == piece["samples"].tensors[0].shape[2:]
        calls.append(window)
        return piece["samples"]

    with patch.object(upscale, "sample_piece", side_effect=sample):
        output, _ = process(video, audio, [], sp, None, noise, None, torch.tensor([1., 0.]), None, 1., latent_start=4)
    assert len(calls) > 1
    assert output.shape == video.shape
    print("PASS", process.__name__, len(calls), "tiles: source offset, resized mask, region noise")
print("PASS original 107-frame mask / 40-frame chunk regression")
