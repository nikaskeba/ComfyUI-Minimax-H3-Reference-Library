import json
import math
import unittest
from unittest.mock import patch

import torch

from test_prompt_resolution import MODULE


def audio(seconds, sr=32000):
    return {"waveform": torch.arange(round(seconds * sr), dtype=torch.float32).repeat(1, 2, 1),
            "sample_rate": sr}


class VoiceCropTests(unittest.TestCase):
    def build(self, count, mode="deterministic", durations=None, **kwargs):
        records = {str(i): dict(reference_type="character", built_in=True,
                               name=f"Person {i}", image_description=f"Person {i}",
                               audio_file=f"{i}.wav") for i in range(count)}
        records["silent"] = dict(reference_type="character", audio_file="silent.wav")
        records["text"] = dict(reference_type="character", audio_description="A quiet voice.")
        definitions = "\n".join("{"+tag+"}" for tag in records)
        detail = "\n".join(f"{{{i}}} says \u00a7{i}\u00a7, <d>[English]Hello.</d>" for i in range(count))
        if count:
            detail += "\n{0} replies \u00a70\u00a7, <d>[English]Again.</d>"
        detail += "\n{text} says \u00a7text\u00a7, <d>[English]Quiet.</d>"
        source = "\n\n".join(h+":\n"+v for h,v in zip(
            ("subject_definitions", "summary", "retention_analysis", "detailed_description",
             "overall_soundscape", "non_diegetic_music"),
            (definitions, "", "N/A", detail, "", "N/A")))
        # Legacy may intentionally load ordinary attached-audio tags; use only
        # the requested voice tags when exercising its already-selected outputs.
        if mode == "legacy":
            source = " ".join(f"\u00a7{i}\u00a7" for i in range(count)) + " \u00a7text\u00a7"
        sources = {f"{i}.wav": audio((durations or {}).get(i, 20)) for i in range(count)}
        with patch.object(MODULE, "records_by_tag", return_value=records), \
             patch.object(MODULE, "library_built_in_records", return_value={}), \
             patch.object(MODULE, "media_path", side_effect=lambda r,k:r[k+"_file"]), \
             patch.object(MODULE, "load_audio", side_effect=lambda path:sources[path]) as loader:
            result = MODULE.H3TaggedReferencePrompt().build(source, compiler_mode=mode, **kwargs)
        return result, sources, loader.call_count

    def test_budget_both_modes_and_short_clip_without_redistribution(self):
        for mode in ("legacy", "deterministic"):
            for count in (1, 2, 3):
                with self.subTest(mode=mode, count=count):
                    result, sources, calls = self.build(count, mode, durations={0:3})
                    self.assertEqual(calls, count)
                    for i in range(count):
                        expected = min(sources[f"{i}.wav"]["waveform"].shape[-1], round(15/count*32000))
                        self.assertEqual(result[11+i]["waveform"].shape, (1,2,expected))
                        self.assertTrue(torch.equal(result[11+i]["waveform"], sources[f"{i}.wav"]["waveform"][...,:expected]))
                        self.assertEqual(sources[f"{i}.wav"]["waveform"].shape[-1], (3 if i==0 else 20)*32000)
                    self.assertEqual([a["max_duration_seconds"] for a in result[20]["audios"]], [15/count]*count)

    def test_all_long_clips_fill_budget(self):
        for count in (1,2,3):
            result, _, _ = self.build(count)
            self.assertEqual(sum(a["waveform"].shape[-1]/a["sample_rate"] for a in result[11:11+count]), 15)

    def test_deferred_off_and_empty_keep_ownership(self):
        result, _, _ = self.build(3)
        deferred, _, calls = self.build(3, defer_media_loading=True)
        self.assertEqual(calls, 0)
        self.assertEqual(result[:2], deferred[:2])
        self.assertEqual(result[20]["audios"], deferred[20]["audios"])
        off, _, _ = self.build(3, auto_crop_voice_references=False)
        self.assertEqual(result[0], off[0])
        for key in ("resources", "audio", "pictures", "speakers"):
            self.assertEqual(json.loads(result[1])[key], json.loads(off[1])[key])
        self.assertTrue(all(a["waveform"].shape[-1]==20*32000 for a in off[11:14]))
        self.assertTrue(all("max_duration_seconds" not in a for a in off[20]["audios"]))
        empty, _, calls = self.build(0)
        self.assertEqual(calls, 0)
        self.assertEqual(empty[20]["audios"], [])
        node = MODULE.H3TaggedReferencePrompt
        self.assertNotEqual(node.IS_CHANGED("x"), node.IS_CHANGED("x", auto_crop_voice_references=False))
        reused, _, _ = self.build(1, compiler_audio_usage="reuse")
        self.assertEqual(reused[11]["waveform"].shape[-1],20*32000)
        self.assertNotIn("max_duration_seconds",reused[20]["audios"][0])

    def test_video_soundtrack_stays_full_and_outside_voice_budget(self):
        records = {"voice":dict(reference_type="character",audio_file="voice.wav"),
                   "clip":dict(reference_type="video",video_file="clip.mp4",video_has_audio=True)}
        source="subject_definitions:\n{voice}\nsummary:\n{clip}\nretention_analysis:\nN/A\ndetailed_description:\n{voice} says \u00a7voice\u00a7, <d>[English]Hi.</d>\noverall_soundscape:\n\u00a7clip\u00a7\nnon_diegetic_music:\nN/A"
        soundtrack=audio(20)
        with patch.object(MODULE,"records_by_tag",return_value=records), \
             patch.object(MODULE,"library_built_in_records",return_value={}), \
             patch.object(MODULE,"media_path",side_effect=lambda r,k:r[k+"_file"]), \
             patch.object(MODULE,"load_audio",return_value=audio(20)), \
             patch.object(MODULE,"load_video",return_value=("frames",soundtrack)):
            result=MODULE.H3TaggedReferencePrompt().build(source,compiler_mode="deterministic")
        self.assertIs(result[17],soundtrack)
        self.assertEqual(result[11]["waveform"].shape[-1],15*32000)
        self.assertNotIn("max_duration_seconds",result[20]["videos"][0])
        self.assertEqual(json.loads(result[1])["resources"]["saved:voice"]["audio"],2)

    def test_reused_voices_and_music_not_cropped_or_counted(self):
        records = {
            "voice": dict(reference_type="character", name="Voice", audio_file="voice.wav"),
            "reuse": dict(reference_type="character", name="Reuse", audio_file="reuse.wav", audio_usage="reuse"),
            "music": dict(reference_type="music", audio_file="music.wav"),
        }
        sources = {k+".wav":audio(20) for k in records}
        for mode in ("legacy", "deterministic"):
            source = "\u00a7voice\u00a7 \u00a7reuse\u00a7 {music}"
            if mode=="deterministic":
                source = "subject_definitions:\n{voice}\n{reuse}\nsummary:\n\nretention_analysis:\nN/A\ndetailed_description:\n{voice} says \u00a7voice\u00a7, <d>[English]Hi.</d> {reuse} says \u00a7reuse\u00a7, <d>[English]Bye.</d>\noverall_soundscape:\n\nnon_diegetic_music:\n{music}"
            with patch.object(MODULE, "records_by_tag", return_value=records), \
                 patch.object(MODULE, "library_built_in_records", return_value={}), \
                 patch.object(MODULE, "media_path", side_effect=lambda r,k:r[k+"_file"]), \
                 patch.object(MODULE, "load_audio", side_effect=lambda p:sources[p]):
                result=MODULE.H3TaggedReferencePrompt().build(source, compiler_mode=mode)
            entries=result[20]["audios"]
            for entry, value in zip(entries,result[11:14]):
                expected=15 if entry["tag"]=="voice" else 20
                self.assertEqual(value["waveform"].shape[-1],expected*32000)
                self.assertEqual(entry.get("max_duration_seconds"),15 if expected==15 else None)

    def test_sample_rates_short_sources_and_copies(self):
        for sr in (24000,32000,44100,48000):
            source=audio(8,sr)
            cropped=MODULE.crop_voice_reference(source,3.00001)
            self.assertEqual(cropped["sample_rate"],sr)
            self.assertEqual(cropped["waveform"].shape,(1,2,math.floor(3.00001*sr)))
            cropped["waveform"][...,0]=-1
            self.assertEqual(source["waveform"][0,0,0].item(),0)
            self.assertIs(MODULE.crop_voice_reference(source,15),source)
            self.assertIs(MODULE.crop_voice_reference(source,None),source)


if __name__ == "__main__":
    unittest.main()
