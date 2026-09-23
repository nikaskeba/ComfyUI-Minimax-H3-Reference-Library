import hashlib
import json
import unittest
import test_playlist_editor as base
from test_disk_video import inspect


class TrimTests(unittest.TestCase):
    setUp=base.PlaylistEditorTests.setUp
    payload=base.PlaylistEditorTests.payload

    def trim(self):
        timeline=[dict(e) for e in self.doc['timeline']]
        timeline[1].update(in_frame=24,out_frame=60)
        return base.editor.edit_timeline(self.token,{'action':'set','revision':self.doc['revision'],'timeline':timeline})

    def test_trim_persists_and_undo_restores_full_clip(self):
        path=base.disk.playlist_media(self.token,self.doc['clips'][1]['clip_id']);digest=hashlib.sha256(path.read_bytes()).digest()
        doc=self.trim();self.assertEqual(doc['timeline'][1]['in_frame'],24)
        restored=base.editor.edit_timeline(self.token,{'action':'undo','revision':doc['revision']})
        self.assertEqual(restored['timeline'],self.doc['timeline'])
        self.assertEqual(hashlib.sha256(path.read_bytes()).digest(),digest)

    def test_empty_and_outside_ranges_rejected_without_history_change(self):
        for start,end in [(24,24),(-1,24),(0,100),(0,2.5)]:
            timeline=[dict(e) for e in self.doc['timeline']];timeline[0].update(in_frame=start,out_frame=end)
            with self.assertRaisesRegex(ValueError,'trim'):
                base.editor.edit_timeline(self.token,{'action':'set','revision':self.doc['revision'],'timeline':timeline})
        self.assertEqual(base.disk.playlist_manifest(self.token)[1]['timeline'],self.doc['timeline'])

    def test_export_uses_trimmed_frames_and_audio(self):
        doc=self.trim()
        result=base.disk.CompilePlaylist().compile(self.token,json.dumps(doc['timeline']))
        output=self.directory/result['result'][0]
        self.assertEqual(inspect(output)[0],72+36+72)

    def test_bridges_and_sections_use_visible_boundaries(self):
        doc=self.trim()
        payload=self.payload(revision=doc['revision'],edit={'mode':'insert_between','side':'after','start':0,'end':0})
        result=base.editor.prepare_redo(self.token,payload)
        spec=json.loads(result['graph']['1']['inputs']['request'])
        self.assertAlmostEqual(spec['neighbors']['previous']['start_seconds'],60/24-22/24)
        payload=self.payload(revision=doc['revision'],edit={'mode':'replace','start':.25,'end':1})
        result=base.editor.prepare_redo(self.token,payload);spec=json.loads(result['graph']['1']['inputs']['request'])
        self.assertEqual(spec['edit']['source_start'],24)
        self.assertEqual(spec['edit']['start_frame'],30)
        self.assertEqual(spec['edit']['end_frame'],48)
        self.assertEqual(spec['edit']['source_frames'],60)
        self.assertEqual(spec['neighbors']['previous']['frames'],5)
        self.assertEqual(spec['neighbors']['next']['start_seconds'],2)

    def test_section_alternate_retains_only_visible_source(self):
        from test_playlist_sections import SectionTests
        doc=self.trim()
        result=base.editor.prepare_redo(self.token,self.payload(revision=doc['revision'],duration=1,edit={'mode':'replace','start':.25,'end':1}))
        request=result['graph']['1']['inputs']['request']
        images,audio=SectionTests.generated(self,1)
        saved=base.editor.PlaylistRedoSave().save(images,request,audio=audio)['result'][0]
        self.assertEqual(inspect(base.disk.playlist_media(self.token,saved))[0],6+24+12)
        _,doc=base.disk.playlist_manifest(self.token)
        adopted=base.editor.edit_timeline(self.token,{'action':'adopt','revision':doc['revision'],'clip_id':saved})
        self.assertNotIn('in_frame',adopted['timeline'][1])
