"""CPU tests for H3 Seam Exposure Match."""

import importlib.util
import math
import os

import torch


_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(os.path.dirname(_TESTS_DIR), "seam_exposure.py")
spec = importlib.util.spec_from_file_location("h3mc_seam_exposure", _MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Components:
    def __init__(self, images):
        self.images = images


class Video:
    def __init__(self, images):
        self.components = Components(images)

    def get_components(self):
        return self.components


def accumulation(images):
    return {"accum": [Video(images)]}


def main():
    node = module.H3SeamExposureMatch()
    images = torch.full((30, 4, 5, 3), 0.4)

    (first_clip,) = node.match(images, accumulation=None)
    assert first_clip is images
    (disabled,) = node.match(images, strength=0.0,
                             accumulation=accumulation(images))
    assert disabled is images

    previous = torch.full((12, 4, 5, 3), 0.5)
    (matched,) = node.match(images, strength=0.75, fade_frames=24,
                            accumulation=accumulation(previous))
    expected_gain = 2.0 ** (0.25 * 0.75)
    assert math.isclose(float(matched[0, 0, 0, 0]),
                        0.4 * expected_gain, rel_tol=1e-5)
    assert torch.equal(matched[23], images[23])
    assert torch.equal(matched[24:], images[24:])
    assert matched.dtype == images.dtype and matched.device == images.device

    close = torch.full_like(previous, 0.405)
    (deadband,) = node.match(images, accumulation=accumulation(close))
    assert deadband is images

    dark = torch.full_like(images, 0.1)
    bright = torch.full_like(previous, 0.9)
    (clamped,) = node.match(dark, strength=1.0, fade_frames=24,
                            accumulation=accumulation(bright))
    assert math.isclose(float(clamped[0, 0, 0, 0]),
                        0.1 * (2.0 ** 0.25), rel_tol=1e-5)

    color = torch.tensor([0.2, 0.4, 0.6]).reshape(1, 1, 1, 3).repeat(30, 4, 5, 1)
    color_reference = color[:6] * 1.1
    (color_matched,) = node.match(
        color, strength=1.0, fade_frames=24,
        accumulation=accumulation(color_reference))
    assert torch.allclose(color_matched[0, ..., 1] / color_matched[0, ..., 0],
                          torch.full((4, 5), 2.0))
    assert torch.allclose(color_matched[0, ..., 2] / color_matched[0, ..., 0],
                          torch.full((4, 5), 3.0))
    assert float(color_matched.min()) >= 0.0
    assert float(color_matched.max()) <= 1.0

    half = images.half()
    (half_matched,) = node.match(
        half, accumulation=accumulation(previous.half()))
    assert half_matched.dtype == torch.float16

    wrong_size = torch.full((6, 3, 5, 3), 0.5)
    try:
        node.match(images, accumulation=accumulation(wrong_size))
    except ValueError as error:
        assert "clip resolutions must agree" in str(error)
    else:
        raise AssertionError("resolution mismatch was accepted")

    print("seam exposure: pass-through, clamp, fade, color, dtype verified")


if __name__ == "__main__":
    main()

