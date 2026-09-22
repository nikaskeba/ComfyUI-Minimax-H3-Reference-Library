"""Check installed AV-bank compatibility against the native H3 packed layout."""
import ast
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent.parent))
import torch
from comfy.ldm.minimax.model import PackedLayout, pack_audio

PATCH = ROOT.parent / 'comfyui-h3-multishot/h3_avbank_probe.py'


@unittest.skipUnless(PATCH.exists(), 'Optional H3 Multishot is not installed')
class AVBankAudioTests(unittest.TestCase):
    def test_connector_and_reference_audio_match_native_layout(self):
        # Execute the installed wrapper in isolation, never patching the real model.
        class LegacyModel:
            def extra_conds(self, **kwargs):
                refs = kwargs.get('minimax_refs') or []
                return {'minimax_payload':types.SimpleNamespace(cond={
                    'cond_audio_latents':[r['audio_latent'] for r in refs if r.get('audio_latent') is not None]})}
        tree = ast.parse(PATCH.read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_apply_merge_patch')
        namespace = {'_mb':types.SimpleNamespace(MiniMaxH3=LegacyModel), '_MC_MARKER':'_h3_motion_context_payload_patch'}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(PATCH), 'exec'), namespace)
        namespace['_apply_merge_patch']()
        reference_audio = torch.full((1,32,2,400), 3.)
        for count in (1,2):
            for voice in (False,True):
                with self.subTest(connectors=count, voice=voice):
                    keys=[{'resolved_frame_index':index*255, 'latent':torch.zeros(1,24,7,2,2),
                           'audio_latent':torch.full((1,32,2,36),float(index+1))} for index in range(count)]
                    refs=([{'kind':'audio','ref_audio_t':400,'audio_latent':reference_audio}]
                          if voice else [{'kind':'image','latent_h':2,'latent_w':2,'latent':torch.zeros(1,24,1,2,2)}])
                    payload=LegacyModel().extra_conds(minimax_keyframes=keys,minimax_refs=refs)['minimax_payload'].cond
                    rows=torch.cat([pack_audio(z) for z in payload['cond_audio_latents']])
                    layout=PackedLayout(4,82,2,2,459,keyframes=keys,refs=refs)
                    expected=int((~layout.audio_update).sum())
                    self.assertEqual(rows.shape,(expected,32))
                    target=torch.empty(layout.audio_update.numel(),32)
                    target[~layout.audio_update]=rows  # The exact assignment that failed.
                    for index in range(count):
                        self.assertTrue(torch.all(rows[index*72:(index+1)*72]==index+1))
                    if voice:self.assertTrue(torch.all(rows[count*72:]==3))
                    if count==1 and voice:self.assertEqual(expected,872)


if __name__=='__main__':unittest.main()
