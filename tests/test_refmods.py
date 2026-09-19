import copy
import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
from safetensors.torch import save_file
from test_cached_h3_reference_node import NODE_MODULE as encoder, _Clip, _VAE

ROOT = Path(__file__).parents[1]
PACKAGE = "h3_refmod_tests"
pkg = types.ModuleType(PACKAGE)
pkg.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = pkg
library = importlib.import_module(PACKAGE + ".refmod_library")
runtime = importlib.import_module(PACKAGE + ".refmod_runtime")
support = importlib.import_module(PACKAGE + ".refmod_support")
apply = importlib.import_module(PACKAGE + ".refmod_apply")
builder = importlib.import_module(PACKAGE + ".h3_tag_references")
create = importlib.import_module(PACKAGE + ".refmod_create")


class RefModTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.roots = patch.object(library, "roots", return_value=[self.root])
        self.roots.start(); self.addCleanup(self.roots.stop)
        self.cache = patch.object(importlib.import_module(encoder.__package__ + ".reference_cache"), "cache_root", return_value=self.root / "cache")
        self.cache.start(); self.addCleanup(self.cache.stop)
        self.model = self.root / "vae.bin"; self.model.write_bytes(b"vae")
        self.clip = _Clip(self.model)
        self.vae = _VAE(self.model)
        self.vae.decode = lambda z: torch.ones(5 if z.shape[2] > 1 else 1, 64, 64, 3)
        self.audio_vae = _VAE(self.model, audio=True)
        self.audio_vae.decode = lambda z: torch.ones(1, int(z.shape[-1] / 40 * 32000), 2)
        self.audio_vae.encode = lambda w: torch.ones(1, 32, 2, round(w.shape[1] / 32000 * 40))

    def asset(self, name, kind="image", seconds=20, bundle=False):
        latent = torch.arange(24 * 2 * 4 * 4, dtype=torch.float32).reshape(1,24,2,4,4)
        if kind == "image": latent = latent[:, :, :1].contiguous()
        if kind == "audio": latent = torch.ones(1,32,2,round(seconds*40))
        meta = dict(name=name, kind=kind, latent_t=latent.shape[-1] if kind == "audio" else latent.shape[2], latent_h=4, latent_w=4)
        if bundle: meta = {"kind": "bundle", "members": [meta, dict(meta, name=name+"2")]}
        path = self.root / (name + ".safetensors")
        tensors = {"ref_0": latent, "ref_1": latent.clone()} if bundle else {"latent": latent}
        save_file(tensors, str(path), metadata={"refmod_meta": json.dumps(meta)})
        return {"file": path.name, "member": 1 if bundle else None}

    def record(self, name, kind="image", seconds=20):
        channel = "voice" if kind == "audio" else "appearance"
        return dict(id=name, tag=name, reference_type="character", image_description=name,
                    **{channel+"_source": "refmod", channel+"_refmod": self.asset(name, kind, seconds)})

    def build(self, records, mode="deterministic", voices=()):
        prompt = "subject_definitions:\n" + "\n".join("{"+tag+"}" for tag in records)
        prompt += "\ndetailed_description:\n" + "\n".join("{"+tag+"} says, <d>[English §"+tag+"§]Hello.</d>" for tag in voices)
        prompt += "\noverall_soundscape:\nQuiet.\nnon_diegetic_music:\nN/A"
        with patch.object(builder, "records_by_tag", return_value=records), patch.object(builder, "library_built_in_records", return_value={}):
            return builder.H3TaggedReferencePrompt().build(prompt, compiler_mode=mode)

    def test_delete_selected_files_preserves_thumbnail_and_checks_all_paths(self):
        visual=self.asset("delete_visual","video")
        audio=self.asset("delete_audio","audio",seconds=1)
        thumbnail=self.root/"delete.png";thumbnail.write_bytes(b"image")
        with self.assertRaises(ValueError):
            library.delete_files([visual,{"file":"../outside.safetensors"}])
        self.assertTrue((self.root/visual["file"]).exists())
        library.delete_files([visual,audio])
        self.assertFalse((self.root/visual["file"]).exists())
        self.assertFalse((self.root/audio["file"]).exists())
        self.assertTrue(thumbnail.exists())

    def test_shared_pair_thumbnail_and_exact_precedence(self):
        visual=self.asset("celestial_visual","video")
        self.asset("celestial_audio","audio",seconds=1)
        shared=self.root/"celestial.png"; shared.write_bytes(b"shared")
        self.assertTrue(all(row["preview"] for row in library.catalog()))
        self.assertEqual(library.preview_path(self.root/visual["file"]),shared)
        exact=self.root/"celestial_visual.webp";exact.write_bytes(b"exact")
        self.assertEqual(library.preview_path(self.root/visual["file"]),exact)

    def test_silent_voice_and_repeated_tags_both_modes(self):
        for mode in ("legacy", "deterministic"):
            records = {"a": self.record("a", "audio"), "silent": self.record("silent", "audio")}
            records["silent"]["voice_refmod"]["file"] = "missing.safetensors"
            output = self.build(records, mode, ["a", "a"])
            self.assertEqual(len(output[21]), 1)
            self.assertEqual(output[20]["audios"][0]["max_duration_seconds"], 15)
            self.assertNotIn("silent", [r["tag"] for r in output[20]["audios"]])

    def test_four_video_refmods_numbered_and_raw_limit_unchanged(self):
        for mode in ("legacy", "deterministic"):
            records = {str(i): self.record(str(i), "video") for i in range(4)}
            output = self.build(records, mode)
            self.assertEqual(len(output[20]["videos"]), 4)
            self.assertIn("<Video 4>", output[0])
            records = {str(i): dict(reference_type="character", video_file="x.mp4") for i in range(4)}
            with self.assertRaisesRegex(ValueError, "3"):
                self.build(records, mode)

    def test_caps_cache_and_prepared_apply(self):
        for count in (1,2,3):
            records = {str(i): self.record(str(i), "audio", 3 if i == 0 and count > 1 else 20) for i in range(count)}
            output = self.build(records, voices=list(records))
            blocks = []
            for entry in output[20]["audios"]:
                _, block, first = encoder._prepare_refmod(entry, self.clip, self.vae, self.audio_vae, "auto", 24)
                _, again, hit = encoder._prepare_refmod(entry, self.clip, self.vae, self.audio_vae, "auto", 24)
                self.assertIn("HIT", hit)
                expected = 3 if entry["tag"] == "0" and count > 1 else 15/count
                self.assertEqual(block["audio_latent"].shape[-1], expected*40)
                self.assertTrue(torch.equal(block["audio_latent"], again["audio_latent"]))
                blocks.append(block)
            native = {"kind": "image", "latent": torch.zeros(1)}
            cond = [[torch.zeros(1), {"minimax_refs": [native, *blocks], "keyframe": "keep"}]]
            first = apply._apply_bound(cond, output[21], 0.7, None, -1, 0)
            second = apply._apply_bound(first, output[21], 0.7, None, -1, 0)
            self.assertEqual(len(second[0][1]["minimax_refs"]), count+1)
            self.assertIs(second[0][1]["minimax_refs"][0], native)
            self.assertEqual(second[0][1]["keyframe"], "keep")
            for a,b in zip(first[0][1]["minimax_refs"][1:],second[0][1]["minimax_refs"][1:]):
                self.assertTrue(torch.equal(a["audio_latent"],b["audio_latent"]))
            entry = copy.deepcopy(output[20]["audios"][-1]); entry["max_duration_seconds"] = None
            _, full, state = encoder._prepare_refmod(entry, self.clip, self.vae, self.audio_vae, "auto", 24)
            self.assertNotIn("HIT", state)
            self.assertEqual(full["audio_latent"].shape[-1], 800)

    def test_mixed_visual_cache_bundle_members_and_validation(self):
        record = self.record("visual", "video")
        record["appearance_refmod"] = self.asset("bundle", "video", bundle=True)
        out = self.build({"visual": record})
        entry = out[20]["videos"][0]
        with patch.object(self.vae, "decode", wraps=self.vae.decode) as decode:
            item, block, state = encoder._prepare_refmod(entry,self.clip,self.vae,self.audio_vae,"auto",24)
            encoder._prepare_refmod(entry,self.clip,self.vae,self.audio_vae,"auto",24)
            self.assertEqual(decode.call_count,1)
            self.assertEqual(len(item["timestamps"]),item["data"].shape[0])
        cond = [[torch.zeros(1), {"minimax_refs": [block]}]]
        with self.assertRaisesRegex(ValueError,"retain"):
            apply._apply_bound(cond,out[21],0,None,-1,0)
        with self.assertRaisesRegex(ValueError,"bindings"):
            apply._apply_bound([[torch.zeros(1),{}]],out[21],1,None,-1,0)
        record["appearance_refmod"] = self.asset("wrong", "audio")
        with self.assertRaisesRegex(ValueError,"Invalid appearance"):
            self.build({"visual":record})

    def test_bound_scramble_rejected_external_deterministic(self):
        out=self.build({"a":self.record("a"),"b":self.record("b")})
        with self.assertRaisesRegex(ValueError,"scrambled"):
            apply._apply_bound([],out[21],1,None,4,0)
        a=apply._ref_blocks(list(out[21]),1,seed=42,scramble_mode="shuffle")
        b=apply._ref_blocks(list(out[21]),1,seed=42,scramble_mode="shuffle")
        self.assertEqual(len(a),2)
        self.assertTrue(all(torch.equal(x["latent"],y["latent"]) for x,y in zip(a,b)))
        with self.assertRaisesRegex(ValueError,"budget"):
            apply._ref_blocks(list(out[21]),1,max_total_tokens=1)

    def test_mixed_numbering_and_source_selection(self):
        records = {"ordinary": dict(id="ordinary", reference_type="character", image_file="face.png", audio_file="voice.wav", image_description="ordinary"), "mod": self.record("mod", "video"), "silent": self.record("silent", "audio")}
        records["mod"].update(voice_source="refmod", voice_refmod=self.asset("modvoice", "audio"))
        with patch.object(builder, "media_path", side_effect=lambda r,k:self.root / r[k+"_file"]):
            result = self.build(records, voices=["mod", "ordinary"])
        debug=json.loads(result[1].split("\nRefMods require")[0])
        self.assertEqual([a["tag"] for a in result[20]["audios"]],["mod","ordinary"])
        self.assertEqual([a["max_duration_seconds"] for a in result[20]["audios"]],[7.5,7.5])
        self.assertIn("<Video 1>",result[0]); self.assertIn("<Picture 1>",result[0])
        projected=library.project_records(records,"{mod} §mod§")
        self.assertTrue(projected["mod"]["_refmod_audio"])
        records["mod"].update(appearance_source="media",voice_source="media",image_file="normal.png",audio_file="normal.wav")
        normal=library.project_records(records,"{mod} §mod§")["mod"]
        self.assertEqual(normal["image_file"],"normal.png"); self.assertNotIn("_refmod_audio",normal)

    def test_member_source_and_encoder_cache_invalidation(self):
        record=self.record("v","video"); record["appearance_refmod"]=self.asset("members","video",bundle=True)
        out=self.build({"v":record}); entry=out[20]["videos"][0]
        _,_,first=encoder._prepare_refmod(entry,self.clip,self.vae,self.audio_vae,"auto",24)
        changed=copy.deepcopy(entry); changed["refmod"]["member"]=0
        _,_,state=encoder._prepare_refmod(changed,self.clip,self.vae,self.audio_vae,"auto",24)
        self.assertNotIn("HIT",state)
        self.model.write_bytes(b"new-model")
        _,_,state=encoder._prepare_refmod(entry,self.clip,self.vae,self.audio_vae,"auto",24)
        self.assertNotIn("HIT",state)
        (self.root / "members.json").write_text('{"updated":true}')
        _,_,state=encoder._prepare_refmod(entry,self.clip,self.vae,self.audio_vae,"auto",24)
        self.assertNotIn("HIT",state)
        self.assertNotEqual(out[21].bindings,self.build({"v":record})[21].bindings)

    def test_external_apply_config_precedence_and_preset_roundtrip(self):
        mod=runtime.H3RefMod.load(str((self.root/self.asset("preset","video")["file"]).with_suffix("")))
        mod.config={"curve":["constant","linear",0.6],"retention":0.8}
        cond=[[torch.zeros(1),{"minimax_refs":[]}]]
        with patch.object(apply,"refmods_dir",return_value=str(self.root)):
            name=apply._save_graph_preset("test curve",("concept_at_end","ease",0.5))
            self.assertEqual(apply._load_graph_preset(name),("concept_at_end","ease",0.5))
            result=apply.SkebaH3RefModApply.execute(cond,[(mod,1)],override=True,graph_preset=name,retention=0.2)
            expected=mod.ref_block(0.8,curve=("constant","linear",0.6))
            self.assertTrue(torch.equal(result[0][0][1]["minimax_refs"][0]["latent"],expected["latent"]))
            self.assertEqual(apply.SkebaH3RefModApply.define_schema().category,"Skeba AI Nodes - Reference")

    def test_full_encoder_marks_slots_and_apply_rejects_reordering(self):
        out=self.build({"a":self.record("a"),"b":self.record("b","video")})
        with patch.object(encoder.h3,"_empty_av_latent",return_value=({"samples":"empty"},5)):
            result=encoder.SkebaCachedMiniMaxH3ReferenceToVideo.execute(self.clip,self.vae,self.audio_vae,out[0],64,64,5,reference_bundle=out[20])
        refs=result[0][0][1]["minimax_refs"]
        self.assertEqual([r["skeba_refmod_slot"] for r in refs],[0,1])
        apply._apply_bound(result[0],out[21],1,None,-1,0)
        changed=[[result[0][0][0],{**result[0][0][1],"minimax_refs":list(reversed(refs))}]]
        with self.assertRaisesRegex(ValueError,"changed order"):
            apply._apply_bound(changed,out[21],1,None,-1,0)

    def test_creation_round_trip(self):
        record=dict(tag="person", image_file="image.png")
        with patch.object(create,"get_record",return_value=record), patch.object(create,"media_path",return_value="image.png"), patch.object(create,"load_image",return_value=torch.ones(1,64,64,3)), patch.object(create,"roots",return_value=[self.root]):
            result=create.SkebaCreateH3RefMod().create(self.vae,"id","image","My reference",64,15)
        file=result["result"][0]
        path,meta=library.resolve({"file":file,"member":None})
        self.assertEqual(meta["kind"],"image")
        self.assertTrue(path.with_suffix(".png").is_file())
        self.assertEqual(runtime.H3RefMod.load(str(path.with_suffix(""))).kind,"image")


if __name__ == "__main__": unittest.main()
