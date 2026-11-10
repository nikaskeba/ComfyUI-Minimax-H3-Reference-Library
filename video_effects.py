"""Independent Skeba tape, film-grain and digital-video looks."""

import math

import torch
import torch.nn.functional as F
from comfy_api.latest import io

from .tape_fx_engine import TapeEngine


def _slider(name, default, maximum=1.0):
    return io.Float.Input(name, default=default, min=0.0, max=maximum, step=0.01)


def _tape_inputs():
    inputs = []
    for name, spec in TapeEngine.INPUT_TYPES()["required"].items():
        if name in ("image", "format", "seed"):
            continue
        kind, options = spec
        options = dict(options)
        if isinstance(kind, list):
            inputs.append(io.Combo.Input(name, options=kind, **options))
        else:
            cls = {"FLOAT": io.Float, "INT": io.Int, "BOOLEAN": io.Boolean, "STRING": io.String}[kind]
            inputs.append(cls.Input(name, **options))
    return inputs


class SkebaVideoEffects(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="SkebaVideoEffects", display_name="SKEBA Video Effects — Tape / Film / MiniDV",
            category="Skeba/Video",
            inputs=[io.Image.Input("image"),
                    io.DynamicCombo.Input("effect", options=[
                        *[io.DynamicCombo.Option(name, _tape_inputs()) for name in ("VHS", "BetaMax", "LaserDisc")],
                        io.DynamicCombo.Option("Film Grain", [_slider("grain", .25), _slider("grain_size", 1, 4), _slider("color_grain", .15)]),
                        io.DynamicCombo.Option("MiniDV", [_slider("compression", .35), _slider("chroma_loss", .65), _slider("sensor_noise", .08), _slider("interlace", .15)]),
                        io.DynamicCombo.Option("35mm to 1990s TV", [_slider("grain", .2), _slider("softness", .4), _slider("color_bleed", .35), _slider("scanlines", .2), _slider("warmth", .2), _slider("flicker", .08)]),
                    ]),
                    io.Combo.Input("speed", options=["Fast", "Balanced", "Full Resolution"], default="Fast",
                                   tooltip="Fast: 640-pixel processing width/height. Balanced: 1280. Output retains its original dimensions. Fine detail is softer in faster modes."),
                    io.Int.Input("seed", default=0, min=0, max=0xFFFFFFFF),
                    io.Int.Input("frame_offset", default=0, min=0, max=100000000,
                                 tooltip="Starting frame for grain/noise and film flicker. Advance for consecutive chunks to avoid repeating patterns.")],
            outputs=[io.Image.Output("image")])

    @classmethod
    def execute(cls, image, effect, speed="Fast", seed=0, frame_offset=0):
        mode = effect["effect"]
        limit = {"Fast": 640, "Balanced": 1280, "Full Resolution": 0}[speed]
        height, width = image.shape[1:3]
        ratio = min(1.0, limit / max(height, width)) if limit else 1.0
        size = (max(1, round(height * ratio)), max(1, round(width * ratio)))
        if mode in ("VHS", "BetaMax", "LaserDisc"):
            frames = image[..., :3]
            if size != (height, width):
                frames = F.interpolate(frames.movedim(-1, 1), size=size, mode="area").movedim(1, -1)
            options = {key: value for key, value in effect.items() if key != "effect"}
            result = TapeEngine().apply(frames, format=mode.lower(), seed=(seed + frame_offset) % 2**32, **options)[0]
            if size != (height, width):
                result = F.interpolate(result.movedim(-1, 1), size=(height, width), mode="bilinear", align_corners=False).movedim(1, -1)
            if image.shape[-1] == 4:
                result = torch.cat((result, image[..., 3:4]), dim=-1)
            return io.NodeOutput(result)

        output = torch.empty_like(image)
        for index, source in enumerate(image):
            x = source[..., :3].movedim(-1, 0).unsqueeze(0).float()
            if size != (height, width):
                x = F.interpolate(x, size=size, mode="area")
            generator = torch.Generator(device=x.device).manual_seed((seed + (frame_offset + index) * 7919) % 2**63)
            if mode == "MiniDV":
                y = x[:, :1] * .299 + x[:, 1:2] * .587 + x[:, 2:3] * .114
                chroma = x - y
                chroma = F.interpolate(F.interpolate(chroma, size=(x.shape[-2], max(1, x.shape[-1] // 4)), mode="area"), size=x.shape[-2:], mode="nearest")
                x = torch.lerp(x, y + chroma, effect["chroma_loss"])
                levels = 256 - 224 * effect["compression"]
                x = torch.lerp(x, (x * levels).round() / levels, effect["compression"])
                x[:, :, 1::2] = torch.lerp(x[:, :, 1::2], torch.roll(x[:, :, 1::2], 1, -1), effect["interlace"])
                grain, grain_size, color = effect["sensor_noise"], 1, .5
            elif mode == "35mm to 1990s TV":
                sd_height = min(480, x.shape[-2])
                sd_width = min(720, max(1, round(sd_height * width / height)))
                sd = F.interpolate(F.interpolate(x, size=(sd_height, sd_width), mode="area"), size=x.shape[-2:], mode="bilinear", align_corners=False)
                x = torch.lerp(x, sd, .5 + .5 * effect["softness"])
                y = x[:, :1] * .299 + x[:, 1:2] * .587 + x[:, 2:3] * .114
                chroma = x - y
                x = y + torch.lerp(chroma, (chroma + torch.roll(chroma, 2, -1)) * .5, effect["color_bleed"])
                x[:, 0] *= 1 + .08 * effect["warmth"]
                x[:, 2] *= 1 - .1 * effect["warmth"]
                x[:, :, 1::2] *= 1 - .25 * effect["scanlines"]
                x *= 1 + .025 * effect["flicker"] * math.sin((frame_offset + index) * 1.7)
                grain, grain_size, color = effect["grain"], 1.2, .1
            elif mode == "Film Grain":
                grain, grain_size, color = effect["grain"], max(1, effect["grain_size"]), effect["color_grain"]
            else:
                raise ValueError(f"Unknown video effect: {mode}")
            if grain:
                noise_size = (max(1, round(x.shape[-2] / grain_size)), max(1, round(x.shape[-1] / grain_size)))
                noise = torch.randn((1, 4, *noise_size), generator=generator, device=x.device, dtype=x.dtype)
                noise = (noise[:, :1] * (1 - color) + noise[:, 1:] * color) / math.sqrt((1 - color)**2 + color**2)
                if noise_size != x.shape[-2:]:
                    noise = F.interpolate(noise, size=x.shape[-2:], mode="bilinear", align_corners=False)
                x = x + noise * (.08 * grain) * (.35 + .65 * (1 - (x - .5).abs() * 2).clamp(0, 1))
            if size != (height, width):
                x = F.interpolate(x, size=(height, width), mode="bilinear", align_corners=False)
            output[index, ..., :3] = x[0].movedim(0, -1).clamp(0, 1).to(image.dtype)
            if image.shape[-1] == 4:
                output[index, ..., 3] = source[..., 3]
        return io.NodeOutput(output)
