from pathlib import Path
"""Ownership metadata for numbered RefMods, independent of external node packs."""
from .refmod_runtime import load_cached
from .reference_cache import fingerprint, hash_file


class BoundRefMods(list):
    def __init__(self):
        super().__init__()
        self.bindings = []


def source_identity(path):
    sidecar = Path(path).with_suffix(".json")
    return {"latent": hash_file(path), "metadata": hash_file(sidecar) if sidecar.is_file() else None}


def build_mods(bundle):
    mods = BoundRefMods()
    bundle_identity = fingerprint({kind: [{key: value for key, value in entry.items() if key != "binding_id"}
                                         for entry in bundle[kind]]
                                   for kind in ("images", "videos", "audios")})
    for kind in ("images", "videos", "audios"):
        for entry in bundle[kind]:
            selected = entry.get("refmod")
            if not selected:
                continue
            path = selected["path"]
            identity = fingerprint({"bundle": bundle_identity, "source": source_identity(path), "member": selected["member"],
                                    "tag": entry["tag"], "channel": selected["channel"],
                                    "cap": entry.get("max_duration_seconds")})
            entry["binding_id"] = identity
            mods.bindings.append(identity)
            mods.append((load_cached(path[:-len(".safetensors")], selected["member"]), 1.0))
    return mods
