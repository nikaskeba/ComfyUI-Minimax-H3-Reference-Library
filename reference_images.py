"""Ordered visual attachments shared by the library and prompt compiler."""

def reference_images(record):
    primary = record.get("image_file")
    images = ([{"image_file": primary, "description": record.get("image_description", "")}]
              if primary else [])
    if not record.get("_refmod_image") and record.get("appearance_source", "media") != "refmod":
        images.extend(record.get("additional_images") or [])
    return images
