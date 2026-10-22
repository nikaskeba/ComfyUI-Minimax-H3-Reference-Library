import importlib.util
from pathlib import Path

import torch


MODULE_PATH = Path(__file__).resolve().parents[1] / "h3_seam_color_transition.py"
spec = importlib.util.spec_from_file_location("h3_seam_color_transition", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_color_transition_corrects_generated_side_and_fades():
    previous = torch.full((30, 4, 4, 3), 0.5)
    previous[..., 1] = 0.6
    images = torch.full((40, 4, 4, 3), 0.5)
    images[..., 1] = 0.5
    source = images.clone()
    result = module.transition_color(images, previous, 22, 24,
                                     strength=1.0, fade_frames=8,
                                     max_change=0.5)
    assert torch.equal(images, source)
    assert torch.equal(result[:24], source[:24])
    assert result[24, 0, 0, 1] > source[24, 0, 0, 1]
    assert torch.allclose(result[24, ..., 0], source[24, ..., 0])
    assert torch.equal(result[31:], source[31:])
    assert torch.allclose(result[24, ..., 1], previous[-1, ..., 1])


def test_bypass_and_missing_context_are_exact():
    images = torch.rand(16, 3, 3, 3)
    previous = torch.rand(16, 3, 3, 3)
    assert module.transition_color(images, previous, 0, 0) is images
    assert module.transition_color(images, previous, 5, 5, strength=0) is images
    node = module.SkebaH3SeamColorTransition()
    assert node.apply(images, 5, 5, accumulation=None)[0] is images
    assert node.apply(images, 5, 5, accumulation={"accum": []})[0] is images

    class SavedClip:
        def seam_frames(self, count):
            return previous[-count:]

    applied = node.apply(images, 5, 5, strength=0.5,
                         accumulation={"accum": [SavedClip()]})[0]
    assert applied.shape == images.shape
    assert torch.equal(applied[:5], images[:5])


def test_workflow_wires_transition_before_trim():
    import json
    path = MODULE_PATH.parent / "example" / "MainWokflow-Oct211 -alt-upscaler.json"
    workflow = json.loads(path.read_text(encoding="utf-8"))
    graph = next(g for g in workflow["definitions"]["subgraphs"]
                 if g.get("name") == "Process Video")
    nodes = {n["id"]: n for n in graph["nodes"]}
    links = {l["id"]: l for l in graph["links"]}
    color = next(n for n in nodes.values()
                 if n["type"] == "SkebaH3SeamColorTransition")
    trim = next(n for n in nodes.values()
                if n["type"] == "SKEBAMiniMaxH3MotionContextTrim")
    color_image = next(i for i in color["inputs"] if i["name"] == "images")
    trim_image = next(i for i in trim["inputs"] if i["name"] == "images")
    assert links[color_image["link"]]["origin_id"] == -10
    assert links[trim_image["link"]]["origin_id"] == color["id"]
    assert color["widgets_values_named"]["strength"] > 0
    assert color["widgets_values_named"]["fade_frames"] == 24
