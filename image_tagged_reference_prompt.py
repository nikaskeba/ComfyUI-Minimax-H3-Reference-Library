"""Image-only reference tags for MiniMax H3 image prompts."""
import re
import folder_paths
from pathlib import Path

from comfy_api.latest import io

from .built_in_references import library_built_in_records
from .h3_tag_references import load_image
from .library import media_path, records_by_tag
from .refmod_library import preview_path, roots

TAG = re.compile(r"\{([^{}\r\n]+)\}")


def refmod_preview(name):
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("RefMod previews must be inside a registered refmods folder.")
    for root in roots():
        path = (root / relative).resolve()
        if path.is_relative_to(root):
            preview = preview_path(path)
            if preview and preview.resolve().is_relative_to(root):
                return preview
    return None


def image_path(tag, records):
    if tag.startswith("photo:"):
        root = Path(folder_paths.get_input_directory()).resolve()
        path = (root / tag[6:]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("One-time photos must be inside ComfyUI/input.")
        if not path.is_file():
            raise FileNotFoundError(f"Photo does not exist: {tag[6:]}")
        return path
    record = records.get(tag)
    if record:
        if record.get("built_in") or record.get("appearance_source", "media") != "refmod":
            if record.get("image_file"):
                return media_path(record, "image")
        else:
            selection = record.get("appearance_refmod") or {}
            if selection.get("file"):
                path = refmod_preview(selection["file"])
                if path:
                    return path
    elif tag.endswith("_rm"):
        name = tag[:-3]
        for suffix in ("", "_visual", "_video", "_audio"):
            path = refmod_preview(name + suffix + ".safetensors")
            if path:
                return path
        # Filename-only tags also work for RefMods in subfolders.
        if "/" not in name and "\\" not in name:
            for root in roots():
                for path in sorted(root.rglob("*.safetensors")):
                    if path.stem in (name, name + "_visual", name + "_video", name + "_audio"):
                        preview = refmod_preview(path.relative_to(root).as_posix())
                        if preview:
                            return preview
    raise FileNotFoundError(f"Reference {{{tag}}} has no image. Attach an image, or add a RefMod preview image.")


class H3ImageTaggedReferencePrompt(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3ImageTaggedReferencePrompt",
            display_name="H3 Image Tagged Reference Prompt",
            category="Skeba AI Nodes - Reference",
            inputs=[io.String.Input("prompt", default="", multiline=True)],
            outputs=[io.String.Output("prompt")] + [io.Image.Output(f"image_{i}") for i in range(1, 17)],
        )

    @classmethod
    def fingerprint_inputs(cls, prompt):
        records = records_by_tag()
        records.update(library_built_in_records())
        paths = [image_path(tag, records) for tag in dict.fromkeys(TAG.findall(prompt))]
        return tuple((str(path), path.stat().st_size, path.stat().st_mtime_ns) for path in paths)

    @classmethod
    def execute(cls, prompt):
        records = records_by_tag()
        records.update(library_built_in_records())
        slots = {}
        images = []

        def replace(match):
            tag = match.group(1)
            if tag not in slots:
                path = image_path(tag, records)
                if len(images) == 16:
                    raise ValueError("H3 Image Tagged Reference Prompt has 16 image slots; split prompts using more than 16 distinct references.")
                images.append(load_image(path))
                slots[tag] = len(images)
            slot = slots[tag]
            return f"<image {slot}> <subject {slot}>"

        rewritten = TAG.sub(replace, prompt)
        return io.NodeOutput(rewritten, *images, *([None] * (16 - len(images))))


class H3ImagePromptBuilder(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="H3ImagePromptBuilder", display_name="H3 Image Prompt Builder",
                         category="Skeba AI Nodes - Reference",
                         inputs=[io.String.Input("prompt", default="", multiline=True)],
                         outputs=[io.String.Output("prompt")])

    @classmethod
    def execute(cls, prompt):
        return io.NodeOutput(prompt)


def builder_choices():
    records = records_by_tag()
    records.update(library_built_in_records())
    references = []
    for tag, record in records.items():
        try:
            image_path(tag, records)
        except (FileNotFoundError, ValueError):
            continue
        references.append({"tag": tag, "name": record.get("name") or tag,
                           "kind": record.get("reference_type") or "object",
                           "description": record.get("image_description", "")})
    root = Path(folder_paths.get_input_directory()).resolve()
    photos = [p.relative_to(root).as_posix() for p in root.rglob("*")
              if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff")
              and p.resolve().is_relative_to(root)]
    return {"references": sorted(references, key=lambda r: r["tag"].lower()), "photos": sorted(photos)}
