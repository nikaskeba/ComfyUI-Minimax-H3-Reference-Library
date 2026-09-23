"""Project edits, fixed neighbor snapshots, and CPU redo-save integration."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from test_disk_video import disk, video, inspect, ROOT

package = types.ModuleType('playlist_test_package')
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
sys.modules[package.__name__ + '.disk_video'] = disk
spec = importlib.util.spec_from_file_location(package.__name__ + '.playlist_editor', ROOT / 'playlist_editor.py')
editor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(editor)


def template_graph():
    # Minimal topology for registration tests; rendering itself is not mocked here.
    return {
        '1': {'class_type':'SkebaPlaylistRedoInput', 'inputs':{'request':'{}'}},
        '2': {'class_type':'SkebaMiniMaxH3AVConnectorGuideTest', 'inputs':{'latent':['7',1]}},
        '3': {'class_type':'SkebaMiniMaxH3AVConnectorGuideTest', 'inputs':{'positive':['2',0], 'latent':['8',1], 'preserve_upscaled_endpoints':True}},
        '4': {'class_type':'SkebaPlaylistRedoSave', 'inputs':{'images':['5',0], 'audio':['5',1], 'request':['1',0]}},
        '5': {'class_type':'SkebaH3AVConnectorFinalizeTest', 'inputs':{'generated_images':['3',3], 'connector_bundle':['3',1]}},
        '6': {'class_type':'H3TaggedReferencePrompt', 'inputs':{'prompt_template':['1',1]}},
        '7': {'class_type':'SkebaCachedMiniMaxH3ReferenceFirstLast', 'inputs':{'length':['1',2], 'prompt':['6',0]}},
        '8': {'class_type':'SkebaCachedMiniMaxH3ReferenceFirstLast', 'inputs':{'length':['1',2], 'target_latent':['9',0]}},
        '9': {'class_type':'SamplerCustomAdvanced', 'inputs':{'noise':['10',0]}},
        '10': {'class_type':'RandomNoise', 'inputs':{'noise_seed':['1',3]}},
    }


class PlaylistEditorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for method,path in [('get_user_directory',Path(self.temp.name)/'user'), ('get_output_directory',Path(self.temp.name)/'out')]:
            path.mkdir()
            p=patch.object(disk.folder_paths,method,return_value=str(path));p.start();self.addCleanup(p.stop)
        accum=[]
        for i in range(3):
            result=disk.SaveClipToFile().save(video(frames=72),accumulation={'accum':accum} if accum else None,prompt=f'[s=3] Prompt {i}')
            accum.append(result['result'][0])
        self.token=result['ui']['skeba_playlist'][0]
        self.directory,self.doc=disk.playlist_manifest(self.token)
        self.template=editor.register_template('Test',template_graph())['id']

    def payload(self,**kwargs):
        return {'revision':self.doc['revision'],'entry_id':self.doc['timeline'][1]['id'],
                'template':self.template,'prompt':'[s=3] Changed prompt','duration':3,'seed':123,**kwargs}

    def test_delete_file_removes_occurrences_and_history(self):
        clip_id=self.doc['clips'][1]['clip_id'];path=disk.playlist_media(self.token,clip_id)
        timeline=self.doc['timeline']+[{'id':'duplicate','clip_id':clip_id}]
        doc=editor.edit_timeline(self.token,{'revision':self.doc['revision'],'action':'set','timeline':timeline})
        doc=editor.edit_timeline(self.token,{'revision':doc['revision'],'action':'delete','clip_id':clip_id})
        self.assertFalse(path.exists())
        self.assertNotIn(clip_id,[c['clip_id'] for c in doc['clips']])
        for entries in [doc['timeline']]+doc['undo']+doc['redo']:
            self.assertNotIn(clip_id,[e['clip_id'] for e in entries])
        self.assertTrue(disk.playlist_media(self.token,self.doc['clips'][0]['clip_id']).exists())

    def test_delete_blocks_active_generation_and_stale_revision(self):
        editor.prepare_redo(self.token,self.payload())
        clip_id=self.doc['clips'][1]['clip_id']
        with self.assertRaisesRegex(ValueError,'active generation'):
            editor.edit_timeline(self.token,{'revision':self.doc['revision'],'action':'delete','clip_id':clip_id})
        with self.assertRaises(editor.RevisionConflict):
            editor.edit_timeline(self.token,{'revision':-1,'action':'delete','clip_id':clip_id})
        self.assertTrue(disk.playlist_media(self.token,clip_id).exists())

    def test_friendly_labels_stay_stable_after_deletion(self):
        self.assertEqual([c['display_name'] for c in self.doc['clips']],['Clip 1','Clip 2','Clip 3'])
        doc=editor.edit_timeline(self.token,{'revision':self.doc['revision'],'action':'delete','clip_id':self.doc['clips'][0]['clip_id']})
        self.assertEqual([c['display_name'] for c in doc['clips']],['Clip 2','Clip 3'])
        self.assertEqual(doc['clip_label_counts']['Clip'],3)

    def test_remove_registered_workflow_keeps_clips(self):
        editor.remove_template(self.template)
        self.assertFalse((editor.template_root()/(self.template+'.json')).exists())
        self.assertEqual(len(disk.playlist_manifest(self.token)[1]['clips']),3)
        with self.assertRaises(ValueError):editor.remove_template('../outside')

    def test_rename_keeps_directory_and_seed_is_saved(self):
        result=editor.edit_timeline(self.token,{'revision':self.doc['revision'],'action':'rename','name':'New title'})
        self.assertEqual(result['name'],'New title')
        self.assertEqual(disk.playlist_manifest(self.token)[0],self.directory)
        saved=disk.SaveClipToFile().save(video(),seed=0)
        metadata=disk.playlist_manifest(saved['ui']['skeba_playlist'][0])[1]['clips'][0]
        self.assertEqual(metadata['seed'],0)
        inferred=disk.SaveClipToFile().save(video(),execution_prompt={'n':{'class_type':'RandomNoise','inputs':{'noise_seed':1234}}})
        self.assertEqual(disk.playlist_manifest(inferred['ui']['skeba_playlist'][0])[1]['clips'][0]['seed'],1234)

    def test_edit_names_and_new_insert_grouping(self):
        doc={'clips':[{'clip_id':'a'}, {'clip_id':'r','parent_clip_id':'a','media_role':'alternate'},
                      {'clip_id':'r2','parent_clip_id':'r','media_role':'alternate'},
                      {'clip_id':'new','parent_clip_id':'a','media_role':'alternate','redo':{'edit':{'mode':'insert_between'}}}]}
        disk.normalize_project(doc)
        self.assertEqual(doc['clips'][1]['edit_display_name'],'Clip 1 - Redo 1')
        self.assertEqual(doc['clips'][2]['edit_display_name'],'Clip 1 - Redo 2')
        self.assertEqual(doc['clips'][3]['media_role'],'new_clip')
        self.assertEqual(doc['clips'][3]['display_name'],'Clip 2')

    def test_crf_defaults_at_registration_and_queue_preparation(self):
        for value in (None, 0, 18, 27, 51):
            with self.subTest(value=value):
                graph = template_graph()
                graph['4']['inputs']['crf'] = value
                registered = editor.register_template('Quality', graph)['id']
                expected = 18 if value is None else value
                self.assertEqual(editor.read_template(registered)['graph']['4']['inputs']['crf'], expected)
                self.assertEqual(graph['4']['inputs']['crf'], value)
                result = editor.prepare_redo(self.token, self.payload(template=registered))
                self.assertEqual(result['graph']['4']['inputs']['crf'], expected)
        self.assertEqual(editor.read_template(self.template)['graph']['4']['inputs']['crf'], 18)
        # Simulate already-saved templates from the old frontend, without re-registering.
        path = editor.template_root() / (self.template + '.json')
        for missing in (False, True):
            legacy = editor.read_template(self.template)
            if missing:
                legacy['graph']['4']['inputs'].pop('crf', None)
            else:
                legacy['graph']['4']['inputs']['crf'] = None
            path.write_text(json.dumps(legacy), encoding='utf-8')
            original = path.read_bytes()
            result = editor.prepare_redo(self.token, self.payload())
            self.assertEqual(result['graph']['4']['inputs']['crf'], 18)
            self.assertEqual(path.read_bytes(), original)

    def test_migration_does_not_include_alternates(self):
        document={'clips':[{'clip_id':'a'},{'clip_id':'b','parent_clip_id':'a'}]}
        self.assertEqual(disk.normalize_project(document)['timeline'],[{'id':'original_a','clip_id':'a'}])
        document['timeline']=[]
        self.assertEqual(disk.normalize_project(document)['timeline'],[])

    def test_edit_undo_redo_and_revision_conflict(self):
        original=self.doc['timeline']
        changed=editor.edit_timeline(self.token,{'revision':self.doc['revision'],'timeline':list(reversed(original))})
        self.assertEqual(changed['timeline'],list(reversed(original)))
        with self.assertRaises(editor.RevisionConflict):editor.edit_timeline(self.token,{'revision':self.doc['revision'],'timeline':[]})
        undone=editor.edit_timeline(self.token,{'revision':changed['revision'],'action':'undo'})
        self.assertEqual(undone['timeline'],original)
        redone=editor.edit_timeline(self.token,{'revision':undone['revision'],'action':'redo'})
        self.assertEqual(redone['timeline'],changed['timeline'])
        self.assertEqual(len(redone['clips']),3)

    def test_new_clip_survives_undo(self):
        editor.edit_timeline(self.token,{'revision':self.doc['revision'],'timeline':self.doc['timeline'][:1]})
        disk._update_manifest(self.directory,clip={'clip_id':'new','filename':'new.mp4'})
        _,doc=disk.playlist_manifest(self.token)
        undone=editor.edit_timeline(self.token,{'revision':doc['revision'],'action':'undo'})
        self.assertEqual([e['clip_id'] for e in undone['timeline']], [c['clip_id'] for c in self.doc['clips']]+['new'])

    def test_neighbor_modes_and_frame_choices(self):
        for sides in [(),('previous',),('next',),('previous','next')]:
            for frames in [5,22,39,56]:
                result=editor.prepare_redo(self.token,self.payload(**{s:{'enabled':True,'frames':frames,'audio':True} for s in sides}))
                spec=json.loads(result['graph']['1']['inputs']['request'])
                self.assertEqual(set(spec['neighbors']),set(sides))
                self.assertEqual(spec['generation_length']%17,5)
                self.assertGreaterEqual(spec['generation_length'],72+len(sides)*frames)
                for key in ['2','3']:
                    inputs=result['graph'][key]['inputs']
                    self.assertEqual(inputs['bypass'],not bool(sides))
                    self.assertEqual(inputs['context_resize'],'full_frame')
                    self.assertEqual('start_frames' in inputs,'previous' in sides)
                    self.assertEqual('end_frames' in inputs,'next' in sides)
                self.assertTrue(result['graph']['3']['inputs']['preserve_upscaled_endpoints'])

    def test_context_video_audio_exact_duration_and_snapshot(self):
        result=editor.prepare_redo(self.token,self.payload(previous={'enabled':True,'frames':22,'audio':True},next={'enabled':True,'frames':5,'audio':False}))
        spec=json.loads(result['graph']['1']['inputs']['request'])
        editor.edit_timeline(self.token,{'revision':self.doc['revision'],'timeline':list(reversed(self.doc['timeline']))})
        self.assertEqual(spec['neighbors']['previous']['clip_id'],self.doc['clips'][0]['clip_id'])
        images,audio=editor.neighbor_media(spec,'previous')
        self.assertEqual(len(images),22)
        self.assertEqual(audio['waveform'].shape[-1],round(22/24*audio['sample_rate']))
        following,audio=editor.neighbor_media(spec,'next')
        self.assertEqual(len(following),5);self.assertIsNone(audio)
        # Previous tail includes the last red frames; next head begins black.
        self.assertGreater(float(images[-1,...,0].mean()),.8)
        self.assertLess(float(following[0].mean()),.05)

    def test_alternate_saved_without_timeline_change(self):
        result=editor.prepare_redo(self.token,self.payload(duration=1))
        request=result['graph']['1']['inputs']['request']
        output=video(frames=39).get_components()
        saved=editor.PlaylistRedoSave().save(output.images,request,audio=output.audio)
        _,doc=disk.playlist_manifest(self.token)
        self.assertEqual(doc['timeline'],self.doc['timeline'])
        self.assertEqual(len(doc['clips']),4)
        clip=doc['clips'][-1]
        self.assertEqual(clip['parent_clip_id'],self.doc['clips'][1]['clip_id'])
        self.assertEqual(clip['prompt'],'[s=1] Changed prompt')
        self.assertEqual(inspect(self.directory/clip['filename'])[0],24)
        self.assertEqual(doc['jobs'][-1]['state'],'completed')
        self.assertEqual(editor.PlaylistRedoSave().save(output.images,request,audio=output.audio)['result'],saved['result'])
        altered=json.loads(request);altered['visible_frames']=1
        with self.assertRaises(ValueError):editor.PlaylistRedoSave().save(output.images,json.dumps(altered))

    def test_jobs_recover_after_browser_refresh(self):
        result=editor.prepare_redo(self.token,self.payload())
        class Queue:
            def get_current_queue(self):return [],[(0,result['prompt_id'])]
            def get_history(self,**kwargs):return {}
        _,doc=editor.reconcile_jobs(self.token,Queue())
        self.assertEqual(doc['jobs'][-1]['state'],'queued')
        class Failed(Queue):
            def get_history(self,**kwargs):return {result['prompt_id']:{'status':{'messages':[['execution_error',{'exception_message':'GPU failure'}]]}}}
        _,doc=editor.reconcile_jobs(self.token,Failed())
        self.assertEqual(doc['jobs'][-1]['state'],'failed')
        self.assertEqual(doc['jobs'][-1]['error'],'GPU failure')

    def test_prompt_times_include_hidden_head_but_saved_prompt_does_not(self):
        prompt='[s=3] timeline: [Shot 1] At 00:00.000, enter. [Shot 2] At 00:02.000, speak.'
        result=editor.prepare_redo(self.token,self.payload(prompt=prompt,previous={'enabled':True,'frames':22}))
        spec=json.loads(result['graph']['1']['inputs']['request'])
        generated=editor.generation_prompt(spec)
        self.assertIn('[Shot 1] At 00:00.917',generated)
        self.assertIn('[Shot 2] At 00:02.917',generated)
        self.assertEqual(spec['prompt'],prompt)

    def test_template_rejects_loop_and_stale_revision(self):
        graph=template_graph();graph['5']={'class_type':'ForLoopOpen','inputs':{}};graph['2']['inputs']['loop']=['5',0]
        with self.assertRaises(ValueError):editor.register_template('Bad',graph)
        wrong_length=template_graph();wrong_length['7']['inputs']['length']=365
        with self.assertRaisesRegex(ValueError,'generation_length'):editor.register_template('Bad length',wrong_length)
        with self.assertRaises(editor.RevisionConflict):editor.prepare_redo(self.token,self.payload(revision=-1))
        with self.assertRaises(ValueError):editor.prepare_redo(self.token,self.payload(previous={'enabled':True,'frames':23}))

    def test_example_graph_edges_and_redo_paths(self):
        graph=json.loads((ROOT/'example/Playlist_Redo.json').read_text(encoding='utf-8'));nodes={n['id']:n for n in graph['nodes']}
        for link,origin,slot,target,input_slot,typ in graph['links']:
            self.assertIn(link,nodes[origin]['outputs'][slot]['links'])
            self.assertEqual(nodes[target]['inputs'][input_slot]['link'],link)
        self.assertFalse(any('MotionContext' in n['type'] or 'ForLoop' in n['type'] or n['type'] in ['Getter','Setter'] for n in nodes.values()))
        for id in [546,553]:
            length=next(i for i in nodes[id]['inputs'] if i['name']=='length')
            link=next(l for l in graph['links'] if l[0]==length['link'])
            self.assertEqual(link[1:3],[1000,2])
        self.assertTrue(nodes[705]['widgets_values'][-1])


if __name__=='__main__':unittest.main()
