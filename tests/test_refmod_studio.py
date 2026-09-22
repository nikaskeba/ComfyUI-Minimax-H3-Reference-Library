import importlib
import json
import unittest
from unittest.mock import patch

import torch
import torch.nn.functional as F
import test_refmods as fixtures
PACKAGE = fixtures.PACKAGE

studio=importlib.import_module(PACKAGE+".refmod_studio")
training=importlib.import_module(PACKAGE+".refmod_training")


class StudioTests(unittest.TestCase):
    setUp = fixtures.RefModTests.setUp
    asset = fixtures.RefModTests.asset
    record = fixtures.RefModTests.record
    def spec(self, **changes):
        return json.dumps({"file":"library/test.safetensors","name":"Person","mode":"training","grid":4,"steps":2,"resolution":320,"sources":[],**changes})

    def run_studio(self,spec,looks=None,audio=None):
        with patch.object(studio,"roots",return_value=[self.root]), patch.object(studio,"_trimmed_source",side_effect=lambda item: ("audio",audio) if item["file"]=="voice" else ("image",looks)):
            return studio.SkebaRefModStudio().save(spec,vae=self.vae,audio_vae=self.audio_vae)

    def test_multisource_training_and_voice_single_safetensors(self):
        image=torch.rand(1,320,320,3);audio={"waveform":torch.rand(1,2,32000),"sample_rate":32000}
        result=self.run_studio(self.spec(sources=[{"file":"one"},{"file":"two"},{"file":"voice"}],audio_action="replace"),image,audio)
        relative=result["result"][0]
        path,meta,mods=studio.members_from_file({"file":relative,"member":0})
        self.assertEqual(meta["kind"],"bundle");self.assertEqual([m.kind for m in mods],["video","audio"])
        self.assertEqual(mods[0].latent_t,2);self.assertEqual(mods[0].latent_h,4)
        self.assertEqual(mods[1].latent_t,40)
        self.assertEqual(meta["skeba_studio"]["steps"],2)
        self.assertTrue(path.with_suffix(".png").is_file())

    def test_edit_reorder_and_append_preserves_latents_and_voice(self):
        record=self.record("v","video")
        selected=record["appearance_refmod"]
        _,_,old=studio.members_from_file(selected)
        original=old[0].latent.clone()
        output=self.run_studio(self.spec(existing=selected,frames="1,0",description="Updated"))
        _,_,mods=studio.members_from_file({"file":output["result"][0],"member":None})
        self.assertTrue(torch.equal(mods[0].latent,original[:,:,[1,0]]))
        self.assertEqual(mods[0].description,"Updated")
        _,_,unchanged=studio.members_from_file(selected)
        self.assertTrue(torch.equal(unchanged[0].latent,original))

    def test_metadata_overwrite_requires_selected_file(self):
        with self.assertRaisesRegex(ValueError,"Select an existing"):
            self.run_studio(self.spec(overwrite=True))
        selected=self.asset("existing")
        out=self.run_studio(self.spec(existing=selected,overwrite=True,description="changed"))
        self.assertEqual(out["result"][0],selected["file"])
        _,meta,_=studio.members_from_file(selected)
        self.assertEqual(meta["description"],"changed")

    def test_duplicate_save_fails_without_overwriting(self):
        selected=self.asset("existing")
        original=(self.root/selected["file"]).read_bytes()
        with self.assertRaisesRegex(ValueError,"already exists"):
            self.run_studio(self.spec(file=selected["file"],existing=selected))
        self.assertEqual((self.root/selected["file"]).read_bytes(),original)

    def test_append_to_compressed_keeps_existing_frames_exact(self):
        image=torch.rand(1,320,320,3)
        result=self.run_studio(self.spec(sources=[{"file":"one"}]),image)
        selected={"file":result["result"][0],"member":None}
        _,_,before=studio.members_from_file(selected)
        second=self.run_studio(self.spec(file="library/appended.safetensors",existing=selected,sources=[{"file":"two"}]),image)
        _,_,after=studio.members_from_file({"file":second["result"][0],"member":None})
        self.assertEqual(after[0].latent_t,2)
        self.assertTrue(torch.equal(before[0].latent,after[0].latent[:,:,:1]))

    def test_removing_last_audio_keeps_visual_bundle_member_index(self):
        image=torch.rand(1,320,320,3); audio={"waveform":torch.rand(1,2,32000),"sample_rate":32000}
        result=self.run_studio(self.spec(sources=[{"file":"one"},{"file":"voice"}],audio_action="replace"),image,audio)
        selected={"file":result["result"][0],"member":0}
        _,_,before=studio.members_from_file(selected)
        self.run_studio(self.spec(existing=selected,overwrite=True,audio_action="remove"))
        _,meta,after=studio.members_from_file(selected)
        self.assertEqual(meta["kind"],"bundle")
        self.assertEqual(len(after),1)
        self.assertTrue(torch.equal(before[0].latent,after[0].latent))

    def test_paired_files_frame_selection_and_preview(self):
        preview_module=importlib.import_module(PACKAGE+".refmod_preview")
        visual=self.asset("actor_visual", "video")
        audio=self.asset("actor_audio", "audio", seconds=1)
        original=(self.root/visual["file"]).read_bytes()
        output=self.run_studio(self.spec(existing=visual,companion=audio,frame_order=[1],subject_name="Actor",appearance="Red shirt",voice_description="Warm"))
        _,meta,mods=studio.members_from_file({"file":output["result"][0],"member":0})
        self.assertEqual(meta["kind"],"bundle")
        self.assertEqual([m.kind for m in mods],["image","audio"])
        self.assertEqual(mods[0].appearance,"Red shirt")
        with patch.object(preview_module.folder_paths,"get_temp_directory",return_value=str(self.root),create=True):
            result=preview_module.SkebaRefModPreview().preview(self.spec(existing=visual,companion=audio),self.vae,self.audio_vae)
        data=result["ui"]["refmod_preview"][0]
        self.assertEqual(len(data["frames"]),2)
        for entry in data["frames"]+[data["audio"]]:
            self.assertTrue((self.root/entry["subfolder"]/entry["filename"]).is_file())
        self.assertEqual((self.root/visual["file"]).read_bytes(),original)
        bundled=self.run_studio(self.spec(existing=visual,companion=audio,overwrite=True,description="Pair updated"))
        self.assertEqual(bundled["result"][0],"actor.safetensors")
        _,meta,members=studio.members_from_file({"file":"actor.safetensors","member":0})
        self.assertEqual(meta["kind"],"bundle")
        self.assertEqual([m.kind for m in members],["video","audio"])
        self.assertEqual((self.root/visual["file"]).read_bytes(),original)
        with self.assertRaisesRegex(ValueError,"already exists"):
            self.run_studio(self.spec(existing=visual,companion=audio,overwrite=True))

    def test_retrain_stored_and_remove_visual(self):
        visual=self.asset("visual","video");audio=self.asset("voice","audio",seconds=1)
        result=self.run_studio(self.spec(existing=visual,retrain=True,grid=2,frame_order=[1,0]))
        _,_,mods=studio.members_from_file({"file":result["result"][0],"member":None})
        self.assertEqual(mods[0].latent_h,2)
        result=self.run_studio(self.spec(file="voice_only.safetensors",existing=visual,companion=audio,frame_order=[]))
        _,_,mods=studio.members_from_file({"file":result["result"][0],"member":None})
        self.assertEqual([m.kind for m in mods],["audio"])

    def test_multiple_video_sections_and_crop(self):
        frames=torch.arange(48*8*12*3,dtype=torch.float32).reshape(48,8,12,3)
        with patch.object(studio,"source_path",return_value=self.root/"clip.mp4"), patch.object(studio,"load_video",return_value=(frames,None)):
            kind, cropped=studio._trimmed_source({"file":"clip.mp4","start":1,"end":1.5,"mirror":True,"crop":{"x":0,"y":0,"w":.5,"h":1}})
        self.assertEqual(kind,"video")
        self.assertTrue(torch.equal(cropped,frames[24:36].flip(2)[:,:,:6]))
        calls=[]
        def source(item):
            calls.append(item)
            return "video",torch.ones(1,320,320,3)
        with patch.object(studio,"roots",return_value=[self.root]),patch.object(studio,"_trimmed_source",side_effect=source):
            result=studio.SkebaRefModStudio().save(self.spec(sources=[{"file":"clip.mp4","sections":[{"start":1,"end":2},{"start":5,"end":6}]}]),vae=self.vae)
        self.assertEqual([item["start"] for item in calls],[1,5])
        _,_,mods=studio.members_from_file({"file":result["result"][0],"member":None})
        self.assertEqual(mods[0].latent_t,2)

    def test_video_sections_include_matching_soundtracks(self):
        calls=[]
        def source(item):
            calls.append(item)
            if item.get("soundtrack_only"):
                return "audio", {"waveform":torch.ones(1,2,32000),"sample_rate":32000}
            return "video",torch.ones(1,320,320,3)
        with patch.object(studio,"roots",return_value=[self.root]),patch.object(studio,"_trimmed_source",side_effect=source):
            result=studio.SkebaRefModStudio().save(self.spec(sources=[{"file":"clip.mp4","include_audio":True,"sections":[{"start":1,"end":2},{"start":5,"end":6}]}]),vae=self.vae,audio_vae=self.audio_vae)
        self.assertEqual([item["start"] for item in calls if item.get("soundtrack_only")],[1,5])
        _,_,mods=studio.members_from_file({"file":result["result"][0],"member":0})
        self.assertEqual([mod.kind for mod in mods],["video","audio"])
        self.assertEqual(mods[1].latent_t,80)

    def test_paths_stay_in_managed_roots(self):
        with patch.object(studio,"roots",return_value=[self.root]),patch.object(studio,"source_root",return_value=self.root):
            for name in ("../escape.safetensors","C:/escape.safetensors"):
                with self.assertRaises(ValueError):studio.output_path(name)
            with self.assertRaises(ValueError):studio.source_path("../escape.png")

    def test_refinement_decreases_reconstruction_error(self):
        torch.manual_seed(3)
        full=torch.rand(1,24,2,8,8)
        small=training.pool_latent(full,2,4,4)
        before=F.mse_loss(F.interpolate(small,size=full.shape[2:],mode="trilinear",align_corners=False),full)
        with torch.inference_mode():
            optimized=training.optimize_latent(small,full,steps=30)
        after=F.mse_loss(F.interpolate(optimized,size=full.shape[2:],mode="trilinear",align_corners=False),full)
        self.assertLess(after,before)
        self.assertFalse(optimized.requires_grad)

if __name__=="__main__":unittest.main()
