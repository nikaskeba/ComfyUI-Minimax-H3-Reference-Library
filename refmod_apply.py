"""Apply behavior adapted from ComfyUI-MiniMaxH3Mod (MIT); see LICENSES/MiniMaxH3Mod-MIT.txt."""
import os
import json
import random
import math
from dataclasses import replace
from typing import Dict, List, Optional
from comfy_api.latest import io
from .refmod_runtime import CURVE_DIRECTIONS, CURVE_SHAPES, curve_strengths, check_bundle
from .refmod_graph import graph_pnginfo, pil_to_tensor, read_graph_meta, render_debug_grid
from .refmod_library import roots
from .refmod_support import BoundRefMods

RETENTION = {"fully_preserved": 1.0, "partially_preserved": 0.7, "attribute_transfer": 0.4, "weak_reference": 0.15}
def refmods_dir():
    return str(roots()[0])


def _apply_bound(conditioning, mods, retention, curve, scramble_seed, budget):
    """Replace numbered blocks from their prepared (possibly cropped) bases."""
    check_bundle(mods, "SKEBA Apply H3 RefMod")
    if scramble_seed >= 0 and len(mods) > 1:
        raise ValueError("Numbered RefMods cannot be scrambled or subsetted; set scramble_seed to -1.")
    if not isinstance(conditioning, list) or not conditioning:
        raise ValueError("Numbered RefMods require conditioning from SKEBA Cached Reference Encoder.")
    bindings = mods.bindings
    if len(bindings) != len(mods) or len(set(bindings)) != len(bindings):
        raise ValueError("Invalid numbered RefMod ownership bindings.")
    out = []
    for tensor, metadata in conditioning:
        refs = list(metadata.get("minimax_refs", []))
        marked = [r for r in refs if r.get("skeba_refmod_binding")]
        if any(r.get("skeba_refmod_slot", index) != index for index, r in enumerate(refs) if r.get("skeba_refmod_binding")):
            raise ValueError("Numbered RefMod blocks have changed order since encoding. Apply before nodes that reorder reference blocks.")
        if len(marked) != len(bindings) or {r["skeba_refmod_binding"] for r in marked} != set(bindings):
            raise ValueError("RefMod bindings do not match the prepared reference bundle. Connect mods and reference_bundle from the same Tagged Reference Prompt.")
        by_id = {r["skeba_refmod_binding"]: r for r in marked}
        prepared = []
        for binding, (mod, strength) in zip(bindings, mods):
            base = by_id[binding].get("skeba_refmod_base")
            if not base:
                raise ValueError("RefMod is missing its prepared base; encode the reference bundle again.")
            latent = base.get("audio_latent") if mod.kind == "audio" else base.get("latent")
            if latent is None:
                raise ValueError("Prepared RefMod kind does not match its attachment.")
            prepared.append((replace(mod, latent=latent), strength))
        blocks = _ref_blocks(prepared, retention, curve, max_total_tokens=budget)
        if len(blocks) != len(bindings):
            raise ValueError("Apply settings must retain every numbered RefMod. Remove its tag or change its source instead of setting zero retention.")
        replacements = {}
        for binding, block in zip(bindings, blocks):
            replacement = dict(by_id[binding])
            replacement.update(block)
            replacements[binding] = replacement
        updated = dict(metadata)
        updated["minimax_refs"] = [replacements.get(r.get("skeba_refmod_binding"), r) for r in refs]
        out.append([tensor, updated])
    return out

def _check_token_budget(mods, budget):
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or int(budget) != budget:
        raise ValueError("Token budget must be a finite integer.")
    total = sum(mod.token_count for mod, strength in mods if strength > 0)
    if budget < 0:
        raise ValueError("Token budget cannot be negative.")
    if budget and total > budget:
        raise ValueError(f"RefMods require {total} tokens after copies; budget is {budget}. Reduce copies or selected mods.")
    return total


def _graph_presets_dir() -> str:
    """models/refmods/graph_presets — shared curve presets, created on first use."""
    d = os.path.join(refmods_dir(), "graph_presets")
    os.makedirs(d, exist_ok=True)
    return d


def _list_graph_presets() -> List[str]:
    """Graph preset names in the presets folder, for the dropdown.

    Presets are PNGs with the graph embedded in their tEXt metadata (a saved
    debug grid); legacy .json files from before the switch still list.  PNGs
    without a valid graph chunk are skipped so random images dropped in the
    folder don't show up.
    """
    d = _graph_presets_dir()
    try:
        entries = sorted(os.listdir(d))
    except OSError:
        return []
    names = []
    for fn in entries:
        if fn.endswith(".json"):
            names.append(fn[:-5])
        elif fn.endswith(".png") and read_graph_meta(os.path.join(d, fn)) is not None:
            names.append(fn[:-4])
    return names


def _load_graph_preset(name: str) -> Optional[tuple]:
    """Read a graph preset -> (direction, shape, value) or None if invalid.

    Presets are PNG files with the graph embedded in their tEXt metadata (the
    saved debug grid — share the image itself); legacy .json presets still
    load.
    """
    d = _graph_presets_dir()
    meta = read_graph_meta(os.path.join(d, name + ".png"))
    if meta is not None:
        return meta
    try:
        with open(os.path.join(d, name + ".json"), "r",
                  encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    direction, shape = data.get("direction"), data.get("shape")
    if direction not in CURVE_DIRECTIONS or shape not in CURVE_SHAPES:
        return None
    try:
        value = float(data.get("value", 1.0))
    except (TypeError, ValueError):
        return None
    return (direction, shape, value)


def _save_graph_preset(name: str, spec, img=None) -> str:
    """Write a (direction, shape, value) tuple as a PNG preset with tEXt meta.

    The saved file is the debug grid itself (a mini preview of the curve)
    with the graph embedded in its metadata, so sharing the image shares the
    curve.  ``img`` is the rendered grid from Apply; when absent a minimal
    grid is rendered just for the file.
    """
    safe = "".join(c if c.isalnum() or c in "-_" else "_"
                    for c in str(name).strip())
    if not safe:
        return ""
    if img is None:
        img = render_debug_grid(spec)
    img.save(os.path.join(_graph_presets_dir(), safe + ".png"),
             pnginfo=graph_pnginfo(spec))
    return safe


def _saved_curve(cfg: Optional[Dict], key: str) -> Optional[tuple]:
    """(direction, shape, value) from a mod's saved config entry, or None.

    Validates against the known curve names so hand-edited/foreign metadata
    can't inject junk into the Apply or Step Curve nodes — anything invalid
    just falls back to the manual widgets.
    """
    entry = (cfg or {}).get(key)
    if not isinstance(entry, (list, tuple)) or len(entry) != 3:
        return None
    direction, shape, value = entry
    if direction not in CURVE_DIRECTIONS or shape not in CURVE_SHAPES:
        return None
    try:
        return (direction, shape, float(value))
    except (TypeError, ValueError):
        return None


def _ref_blocks(mods, retention, curve=None, seed=-1, scramble_mode="legacy_subset", scramble_keep=1, max_total_tokens=0) -> List[Dict]:
    """Ref blocks for a loader bundle, scaled by row strength x retention.

    ``retention`` is a master strength multiplier: a float 0-1 (1.0 =
    fully_preserved, 0.7 = partially_preserved, 0.4 = attribute_transfer,
    0.15 = weak_reference), or one of those preset names for legacy
    workflows saved with the old combo widget.

    ``curve`` (optional) is a per-frame strength spec — a ``(direction,
    shape, value)`` tuple, a legacy preset name, per-frame values, control
    points (see ``core.curve_strengths``) — applied on top of the row
    strength.  A flat/no curve keeps today's behavior.

    ``seed`` (default -1 = off) enables ref scrambling: with 2+ refs in the
    bundle, the order is shuffled and a random subset kept, so a different
    ref leads each run instead of the same one always "popping".  Same seed
    -> same scramble; connect/randomize the seed for per-run variation.
    """
    if isinstance(retention, str):
        factor = RETENTION.get(retention, 1.0)
    else:
        factor = float(retention)
    items = list(mods)
    if int(seed) >= 0 and len(items) > 1:
        rng = random.Random(int(seed))
        rng.shuffle(items)
        if scramble_mode == "legacy_subset":
            keep = rng.randint(max(1, len(items) // 2), len(items))
            items = items[:keep]
        elif scramble_mode == "subset":
            items = items[:max(1, int(scramble_keep))]
        elif scramble_mode != "shuffle":
            raise ValueError("Unknown scramble mode.")
        print(f"[MiniMaxH3RefModApply] scramble seed={int(seed)}: "
              f"{len(mods)} refs -> kept {len(items)} (order shuffled)")
    _check_token_budget(items, max_total_tokens)
    blocks = []
    notes = []
    summaries = []  # (name, effective average multiplier)
    for mod, strength in items:
        eff = min(1.0, max(0.0, strength * factor))
        used_curve = curve
        if (mod.latent_t <= 1 and isinstance(curve, tuple) and len(curve) == 3
                and isinstance(curve[0], str) and str(curve[0]) != "constant"):
            # curve directions run across a mod's own ref frames, which is
            # meaningless on single-frame mods — previously this silently
            # no-op'ed and identity mods always injected at full strength.
            # Now: treat curve_value as a plain strength cap instead.
            cap = max(0.0, min(1.0, float(curve[2])))
            if cap < eff:
                notes.append(
                    f"'{mod.name}' is image-kind (1 frame): direction "
                    f"'{curve[0]}' has no effect; using curve_value "
                    f"{cap:.2f} as its strength cap instead")
                eff = min(eff, cap)
            used_curve = None
        block = mod.ref_block(eff, curve=used_curve)
        if block is not None:
            # marker the step-curve wrapper uses to tell this ref apart from
            # native ref2va refs (original input video, keyframes, ...) so it
            # only ever re-mixes what the Apply node injected
            block["refmod"] = True
            blocks.append(block)
        avg = eff
        if used_curve is not None and mod.latent_t > 1:
            strengths = curve_strengths(used_curve, mod.latent_t)
            if strengths:
                avg = eff * (sum(strengths) / len(strengths))
        summaries.append((mod.name, avg))
    for line in notes:
        print(f"[MiniMaxH3RefModApply] note: {line}")
    if summaries and any(s < 0.999 for _n, s in summaries):
        detail = ", ".join(f"{n}@{s:.2f}" for n, s in summaries)
        weak = min(s for _n, s in summaries) < 0.3
        print(f"[MiniMaxH3RefModApply] effective ref strength (row x retention"
              f"{' x curve-mean' if curve is not None else ''}): {detail}"
              + ("  <- below 0.30, expect a weak insertion" if weak else ""))
    return blocks


class SkebaH3RefModApply(io.ComfyNode):
    """
    Inject a loader bundle of RefMods into a MiniMax H3 conditioning.

    Accepts either the ComfyUI-MiniMaxH3 pack's MINIMAX_H3_COND or the built-in
    ComfyUI CONDITIONING (from the core MiniMaxH3ReferenceToVideo node) and
    returns the same type.  Appends each mod's reference latent to the
    conditioning's ``refs`` / ``minimax_refs``, so the DiT attends to it
    through all blocks exactly like a reference image/video.  ``retention`` is
    a master strength over the loader's per-row strengths; the curve is split
    into ``curve_direction`` (constant / concept_at_start / concept_at_end),
    ``curve_shape`` (how the envelope travels between its endpoints) and
    ``curve_value`` (the non-zero endpoint) — all plain widgets, no ComfyUI
    Curve widget required.  ``scramble_seed`` (default -1 = off) shuffles the
    ref order and keeps a random subset per run so a multi-ref mod can "pop"
    a different ref each time instead of always the same one.
    """

    @classmethod
    def define_schema(cls):
        template = io.MatchType.Template(
            "cond",
            allowed_types=[io.Custom("MINIMAX_H3_COND"), io.Conditioning])
        return io.Schema(
            node_id="SkebaH3RefModApply",
            display_name="SKEBA Apply H3 RefMod",
            description=(
                "Inject a loader bundle of RefMods into a MiniMax H3 conditioning. "
                "Accepts both the pack's MINIMAX_H3_COND and the built-in "
                "CONDITIONING and returns the same type."
            ),
            category="Skeba AI Nodes - Reference",
            inputs=[
                io.MatchType.Input("conditioning", template=template,
                    tooltip="MINIMAX_H3_COND (ComfyUI-MiniMaxH3 pack) or CONDITIONING "
                            "(core MiniMaxH3ReferenceToVideo)."),
                io.Custom("H3_REF_MODS").Input("mods",
                    tooltip="Bundle from Load H3 RefMods / Load H3 RefMod Axis / Create H3 RefMod."),
                io.Boolean.Input("override", default=False,
                    tooltip="Use the config fixed into the mods' own metadata (by 'Fix H3 RefMod "
                            "Config') instead of the widgets below: retention + curve come from "
                            "the first mod in the bundle that carries one. Handy for sharing mods "
                            "whose magic settings took real tuning. Off (default) = use the manual "
                            "parameters. If no mod has a saved config it falls back to the manual "
                            "parameters and prints a note."),
                io.Float.Input("retention", default=1.0, min=0.0, max=1.0, step=0.01,
                    tooltip="Master reference strength, multiplied with each loader row's "
                             "strength. MiniMax retention levels: 1.0 = fully_preserved, "
                             "0.7 = partially_preserved, 0.4 = attribute_transfer (keep "
                             "style/attributes, not identity), 0.15 = weak_reference. "
                             "0 = no reference."),
                io.Combo.Input("curve_direction", options=list(CURVE_DIRECTIONS),
                    default="constant",
                    tooltip="Weighting envelope across THIS MOD'S OWN ref frames "
                            "(stacked images / video-ref latent frames) — i.e. WHICH "
                            "reference content dominates, NOT where the concept "
                            "appears in the output video (ref tokens are not bound "
                            "to output time; for output-timing control use the 'H3 "
                            "RefMod Step Curve' node instead, which runs over the "
                            "denoise timeline). 'constant' (default) = every ref "
                            "frame at full strength (official-ref parity). The old "
                            "default 'concept_at_end' fades early stack frames toward "
                            "blur, roughly HALVING average strength on multi-frame "
                            "mods. Old saved workflows keep their saved values."),
                io.Int.Input("scramble_seed", default=-1, min=-1, max=2147483647, step=1,
                    control_after_generate=io.ControlAfterGenerate.fixed,
                    tooltip="Ref scrambling seed. -1 (default) = off: all refs in saved order. "
                            "With 2+ refs in the bundle, a seed >= 0 shuffles the ref order and "
                            "keeps a random subset, so a different ref leads each run (a multi-ref "
                            "mod 'pops' a different video/image per seed). Same seed = same "
                            "scramble; set this widget's control-after-generate to 'randomize' "
                            "for per-run variation."),
                io.Combo.Input("curve_shape", options=list(CURVE_SHAPES),
                    default="linear",
                    tooltip="How the weighting travels between its endpoints: 'linear', "
                            "'ease' (smoothstep), 'sigmoid'/'tanh' (S-curves, tanh with a "
                            "steeper knee), 'quadratic', 'cubic', 'exponential', 'stair' "
                            "(stepped), 'elastic' (overshoots), 'bump'/'dip' (peak/trough "
                            "mid-stack). Only matters when curve_direction != constant."),
                io.Float.Input("curve_value", default=1.0, min=0.0, max=1.0, step=0.01,
                    tooltip="Endpoint weight ('user input'): both endpoints for 'constant' and "
                            "'concept_at_ends', the start for 'concept_at_start', the end for "
                            "'concept_at_end', the mid peak for 'concept_at_middle'. On "
                            "single-image ('image'-kind) mods this acts as a simple STRENGTH CAP "
                            "(directions are meaningless on one frame): 0.4 = the ref blends "
                            "40% toward its blurred self."),
                io.Combo.Input("graph_preset",
                    options=["(none)"] + _list_graph_presets(), default="(none)",
                    optional=True,
                    tooltip="Optional shared graph preset — leave on '(none)' to use the curve "
                            "widgets above. Selecting one loads direction/shape/value from a "
                            "saved debug-grid PNG (graph embedded in its metadata) or a legacy "
                            ".json, in models/refmods/graph_presets/. Share the preset PNG "
                            "itself to share a curve. New presets appear after a restart."),
                io.Combo.Input("scramble_mode", options=["shuffle", "subset", "legacy_subset"], default="shuffle", optional=True),
                io.Int.Input("scramble_keep", default=1, min=1, max=80, optional=True, tooltip="Refs retained in subset mode; shuffle keeps all refs."),
                io.Int.Input("max_total_tokens", default=0, min=0, max=1048576, optional=True, tooltip="Total reference token budget after copies; 0 disables the limit."),
                io.String.Input("save_preset_as", default="", optional=True,
                    tooltip="Optional: type a name and run to save the current (resolved) curve "
                            "as a PNG preset — the curve graph itself with the graph embedded in "
                            "its metadata — in models/refmods/graph_presets/. Share that image "
                            "to share the curve. Leave empty to skip."),
            ],
            outputs=[
                io.MatchType.Output(template=template, display_name="conditioning",
                    tooltip="The conditioning with the ref blocks injected, same type as the input."),
                io.Image.Output("debug", display_name="curve graph",
                    tooltip="Optional 1024x1024 curve graph: the strength envelope "
                            "(direction/shape/value) with the concept zone shaded. Leave "
                            "unconnected to skip the preview."),
            ],
        )

    @classmethod
    def execute(cls, conditioning, mods, retention=1.0,
                curve_direction="constant", curve_shape="linear", curve_value=1.0,
                strength_curve=None, scramble_seed=-1, graph_preset="", save_preset_as="",
                override=False, scramble_mode="legacy_subset", scramble_keep=1, max_total_tokens=0):
        # workflows saved before the curve split pass the old single preset name
        curve = strength_curve if strength_curve is not None \
            else (curve_direction, curve_shape, curve_value)
        check_bundle(mods, "SKEBA Apply H3 RefMod")
        # a selected graph preset overrides the curve widgets
        preset_name = ""
        curve_source = "legacy strength_curve" if strength_curve is not None else "widgets"
        retention_source = "widget"
        if graph_preset and graph_preset != "(none)":
            loaded = _load_graph_preset(graph_preset)
            if loaded is None:
                print(f"[MiniMaxH3RefModApply] WARNING: graph preset '{graph_preset}' "
                      f"not found or invalid — using widget curve")
            else:
                curve = loaded
                preset_name = graph_preset
                curve_source = f"graph preset {graph_preset}"
        # override: pull retention + curve from the first mod with a fixed config
        if override:
            found = None
            for m, _s in (mods or []):
                saved = _saved_curve(getattr(m, "config", None), "curve")
                if saved is not None:
                    found = (m, saved)
                    break
            if found is None:
                print("[MiniMaxH3RefModApply] override=True but no valid saved curve "
                      f"was found — keeping {curve_source} and widget retention.")
            else:
                m, saved = found
                cfg = getattr(m, "config", None) or {}
                curve = saved
                curve_source = f"saved config {m.name}"
                if isinstance(cfg.get("retention"), (int, float)):
                    retention_source = f"saved config {m.name}"
                    retention = min(1.0, max(0.0, float(cfg["retention"])))
                print(f"[MiniMaxH3RefModApply] override: using config from '{m.name}' "
                      f"(retention={retention:.2f}, curve={curve[0]} + {curve[1]} "
                      f"@ {float(curve[2]):.2f})")
        ignored = []
        if curve_source != "widgets":
            ignored.append(f"curve_direction, curve_shape, curve_value (using {curve_source})")
        if retention_source != "widget":
            ignored.append(f"retention (using {retention_source})")
        if scramble_seed < 0 or len(mods) < 2:
            ignored.append("scramble_mode, scramble_keep (scrambling inactive)")
        elif scramble_mode in ("shuffle", "legacy_subset"):
            ignored.append(f"scramble_keep ({scramble_mode})")
        if ignored:
            print("[MiniMaxH3RefModApply] ignored: " + "; ".join(ignored))
        img = render_debug_grid(curve, preset_name)
        if save_preset_as:
            saved = _save_graph_preset(save_preset_as, curve, img)
            if saved:
                print(f"[MiniMaxH3RefModApply] graph preset saved: {saved}.png "
                      f"({curve[0]} + {curve[1]} @ {float(curve[2]):.2f})")
        if isinstance(mods, BoundRefMods) and mods:
            return io.NodeOutput(_apply_bound(conditioning, mods, retention, curve,
                                             scramble_seed, max_total_tokens), pil_to_tensor(img))
        blocks = _ref_blocks(mods, retention, curve, seed=scramble_seed,
                             scramble_mode=scramble_mode, scramble_keep=scramble_keep, max_total_tokens=max_total_tokens)
        if isinstance(conditioning, list):
            # built-in ComfyUI CONDITIONING (core MiniMaxH3ReferenceToVideo)
            out = []
            for t in conditioning:
                d = dict(t[1])
                d["minimax_refs"] = list(d.get("minimax_refs", [])) + blocks
                out.append([t[0], d])
            print(f"[MiniMaxH3RefModApply] retention={retention} "
                  f"({len(blocks)} ref block(s) injected)")
        else:
            # ComfyUI-MiniMaxH3 pack MINIMAX_H3_COND
            out = replace(conditioning, refs=list(conditioning.refs) + blocks)
            print(f"[MiniMaxH3RefModApply] retention={retention} "
                  f"({len(blocks)} ref block(s) injected, {len(out.refs)} total)")
        return io.NodeOutput(out, pil_to_tensor(img))

