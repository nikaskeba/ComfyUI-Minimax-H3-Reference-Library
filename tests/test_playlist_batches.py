"""Batch ownership, sequential execution, recovery, and real FFmpeg assembly."""
import asyncio
import copy
import hashlib
import importlib
import json
import sys
import types
import unittest
from unittest.mock import patch

import test_playlist_editor as base
import test_playlist_sections as sections
from test_disk_video import video, inspect

sys.modules[base.package.__name__+'.playlist_editor'] = base.editor
batch = importlib.import_module(base.package.__name__+'.playlist_batches')
editor, disk = base.editor, base.disk


class BatchTests(unittest.TestCase):
    setUp = base.PlaylistEditorTests.setUp
    payload = base.PlaylistEditorTests.payload
    source = sections.SectionTests.source

    def prepare(self, **kwargs):
        return batch.prepare_batch(self.token,self.payload(prompt='[s=1] First | [s=1] Second | [s=1] Last',**kwargs))

    def save_children(self, job):
        previous = None
        for index in range(len(job['segments'])):
            spec = batch.child_spec(job,index,previous)
            directory,doc = disk.playlist_manifest(self.token)
            parent = next(j for j in doc['jobs'] if j['id']==job['id'])
            parent['children'].append(spec['request_id'])
            doc['jobs'].append({'id':spec['request_id'],'state':'running','spec':spec})
            disk.write_project(directory,doc)
            parts = video(frames=spec['visible_frames']+7).get_components()
            editor.PlaylistRedoSave().save(parts.images,json.dumps(spec),audio=parts.audio)
            _,doc = disk.playlist_manifest(self.token)
            previous = doc['clips'][-1]
        batch.finish_batch(self.token,job['id'])
        return disk.playlist_manifest(self.token)[1]

    def test_retry_single_preserves_seed_boundaries_and_template(self):
        prepared=editor.prepare_redo(self.token,self.payload(previous={'enabled':True}))
        editor.update_job(self.token,prepared['request_id'],{'state':'failed','error':'bad prompt'})
        editor.remove_template(self.template)
        server=types.SimpleNamespace(prompt_queue=types.SimpleNamespace(get_current_queue=lambda:([],[]),get_history=lambda **kw:{}))
        retried=batch.retry_job(server,self.token,prepared['request_id'],'[s=2] Fixed prompt')
        spec=json.loads(retried['graph']['1']['inputs']['request'])
        self.assertNotEqual(spec['request_id'],prepared['request_id'])
        self.assertEqual(spec['seed'],123)
        self.assertEqual(spec['duration'],2)
        self.assertEqual(spec['neighbors'],prepared['spec']['neighbors'])
        _,doc=disk.playlist_manifest(self.token)
        self.assertEqual(doc['jobs'][-2]['state'],'failed')
        self.assertEqual(doc['jobs'][-1]['retry_of'],prepared['request_id'])
        self.assertEqual(doc['timeline'],self.doc['timeline'])

    def test_retry_batch_reuses_only_completed_prefix_and_keeps_original(self):
        job=self.prepare()
        directory,doc=disk.playlist_manifest(self.token)
        doc['jobs'][-1].update(state='failed',children=['first-child'])
        spec=batch.child_spec(job,0)
        doc['jobs'].append({'id':'first-child','spec':spec,'state':'completed','clip_id':doc['clips'][0]['clip_id']})
        disk.write_project(directory,doc)
        server=types.SimpleNamespace(prompt_queue=types.SimpleNamespace(get_current_queue=lambda:([],[]),get_history=lambda **kw:{}))
        parts=[s['prompt'] for s in job['segments']];parts[1]='[s=2] Corrected second prompt'
        result=batch.retry_job(server,self.token,job['id'],'|'.join(parts))
        retried=batch.batch_job(self.token,result['batch_id'])
        self.assertEqual(retried['children'],['first-child'])
        self.assertEqual(retried['spec']['duration'],4)
        self.assertEqual(retried['spec']['seed'],job['spec']['seed'])
        self.assertEqual(batch.batch_job(self.token,job['id'])['segments'],job['segments'])
        parts[0]='Different first prompt'
        with self.assertRaisesRegex(ValueError,'already completed'):
            batch.retry_job(server,self.token,job['id'],'|'.join(parts))
        with self.assertRaisesRegex(ValueError,'same number'):
            batch.retry_job(server,self.token,job['id'],'Only one')

    def test_markers_empty_and_defaults(self):
        segments=batch.prompt_segments('One|[s=2.5] Two|[new_location] Three',7)
        self.assertEqual([s['duration'] for s in segments],[7,2.5,7])
        self.assertTrue(segments[2]['scene_change'])
        for text in ('One||Three','One|','|Two'):
            with self.assertRaisesRegex(ValueError,'Prompt .*empty'):batch.prompt_segments(text)
        for text in ('[s=nan] One','[s=-2] One','[s=] One','[s=2][s=3] One'):
            with self.assertRaisesRegex(ValueError,'Prompt 1'):batch.prompt_segments(text)

    def test_boundaries_scene_reset_and_shared_seed(self):
        for before,after in ((False,False),(True,False),(False,True),(True,True)):
            job=self.prepare(previous={'enabled':before},next={'enabled':after})
            first=batch.child_spec(job,0);middle=batch.child_spec(job,1);last=batch.child_spec(job,2)
            self.assertEqual('previous' in first['neighbors'],before)
            self.assertNotIn('next',first['neighbors'])
            self.assertEqual(set(middle['neighbors']),{'previous'})
            self.assertEqual('next' in last['neighbors'],after)
            self.assertEqual([s['seed'] for s in (first,middle,last)],[123]*3)
            self.assertEqual(middle['neighbors']['previous']['frames'],22)
            job['segments'][0]['scene_change']=job['segments'][1]['scene_change']=True
            self.assertEqual('previous' in batch.child_spec(job,0)['neighbors'],before)
            self.assertNotIn('previous',batch.child_spec(job,1)['neighbors'])
            job['continuation']['enabled']=False
            self.assertNotIn('previous',batch.child_spec(job,2)['neighbors'])
            # Both passes receive only their own selected boundaries.
            graph=editor.redo_graph(job['template_snapshot'],last)
            for key in ('2','3'):
                self.assertEqual('end_frames' in graph[key]['inputs'],after)

    def test_short_windows_and_audio_controls(self):
        job=self.prepare(continuation={'frames':56,'audio':False})
        spec=batch.child_spec(job,1,{'clip_id':'short','duration_seconds':.3})
        self.assertEqual(spec['neighbors']['previous']['frames'],5)
        self.assertFalse(spec['neighbors']['previous']['audio'])
        self.assertAlmostEqual(spec['neighbors']['previous']['start_seconds'],.3-5/24)
        self.assertNotIn('previous',batch.child_spec(job,1,{'clip_id':'tiny','duration_seconds':.1})['neighbors'])

    def test_real_assembly_and_adoption_all_modes(self):
        for mode,start,end in (('replace',4,8),('replace',4,5),('replace',0,5),('replace',8,12),('replace',0,12),('insert',6,6),('insert_between',0,0)):
            with self.subTest(mode=mode,start=start):
                path=self.source(fps=30)
                original=hashlib.sha256(path.read_bytes()).hexdigest()
                job=self.prepare(edit={'mode':mode,'start':start,'end':end},previous={'enabled':True},next={'enabled':True})
                doc=self.save_children(job)
                result=doc['clips'][-1]
                expected=90 if mode=='insert_between' else 360-round((end-start)*30)+90
                self.assertEqual(result['frame_count'],expected)
                self.assertEqual(result['fps'],30)
                self.assertAlmostEqual(inspect(disk.playlist_media(self.token,result['clip_id']))[1],expected/30,delta=.025)
                self.assertEqual((result['width'],result['height']),(64,48))
                self.assertEqual(result['seed'],123)
                self.assertEqual(len(result['batch_clips']),3)
                children=[c for c in doc['clips'] if c['clip_id'] in result['batch_clips']]
                self.assertEqual([c['frame_count'] for c in children],[24]*3)
                self.assertEqual(doc['timeline'],self.doc['timeline'])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),original)
                adopted=editor.edit_timeline(self.token,{'revision':doc['revision'],'action':'adopt','clip_id':result['clip_id']})
                self.assertIn(result['clip_id'],[e['clip_id'] for e in adopted['timeline']])
                restored=editor.edit_timeline(self.token,{'revision':adopted['revision'],'action':'undo'})
                self.assertEqual(restored['timeline'],self.doc['timeline'])
                self.doc=restored

    def test_whole_batch_snapshot_and_stale_adoption(self):
        job=self.prepare()
        editor.remove_template(self.template)
        doc=self.save_children(job)
        self.assertEqual(doc['clips'][-1]['frame_count'],72)
        changed=copy.deepcopy(doc['timeline']);changed[1]['out_frame']=48
        doc=editor.edit_timeline(self.token,{'revision':doc['revision'],'timeline':changed})
        with self.assertRaisesRegex(ValueError,'occurrence changed'):
            editor.edit_timeline(self.token,{'revision':doc['revision'],'action':'adopt','clip_id':doc['clips'][-1]['clip_id']})

    def test_active_batch_protects_completed_clip_and_canceled_save(self):
        job=self.prepare()
        spec=batch.child_spec(job,0)
        directory,doc=disk.playlist_manifest(self.token)
        parent=next(j for j in doc['jobs'] if j['id']==job['id'])
        parent['children'].append(spec['request_id'])
        doc['jobs'].append({'id':spec['request_id'],'state':'running','spec':spec})
        disk.write_project(directory,doc)
        parts=video(frames=24,width=80,height=60).get_components()
        editor.PlaylistRedoSave().save(parts.images,json.dumps(spec),audio=parts.audio)
        _,doc=disk.playlist_manifest(self.token)
        clip=doc['clips'][-1]
        self.assertEqual((clip['width'],clip['height']),(64,48))
        with self.assertRaisesRegex(ValueError,'active generation'):
            editor.edit_timeline(self.token,{'revision':doc['revision'],'action':'delete','clip_id':clip['clip_id']})
        batch.set_batch(self.token,job['id'],state='canceled')
        with self.assertRaisesRegex(ValueError,'canceled'):editor.verify_request(spec)
        self.assertTrue(disk.playlist_media(self.token,clip['clip_id']).exists())

    def test_compiler_settings_resolve_validator_and_primitives(self):
        graph={'1':{'class_type':'PrimitiveBoolean','inputs':{'value':True}},
               '2':{'class_type':'SKEBAH3PromptListValidator','inputs':{'validation_enabled':['1',0]}}}
        self.assertEqual(batch.compiler_setting(graph,['2',1]),'deterministic')
        graph['1']['inputs']['value']=False
        self.assertEqual(batch.compiler_setting(graph,['2',1]),'legacy')

    def test_preflight_compiles_all_settings_without_media_decode(self):
        async def scenario():
            job=self.prepare()
            calls=[]
            class Compiler:
                def build(self,prompt_template,compiler_mode='legacy',defer_media_loading=False):
                    calls.append((prompt_template,compiler_mode,defer_media_loading))
            async def validate(identifier,graph,targets):return True,None,['4'],{}
            fake_execution=types.SimpleNamespace(validate_prompt=validate)
            fake_nodes=types.SimpleNamespace(NODE_CLASS_MAPPINGS={'H3TaggedReferencePrompt':Compiler})
            server=types.SimpleNamespace(trigger_on_prompt=lambda p:p,node_replace_manager=types.SimpleNamespace(apply_replacements=lambda g:None))
            with patch.dict(sys.modules,{'execution':fake_execution,'nodes':fake_nodes}):
                for index in range(3):
                    graph,outputs=await batch.checked_graph(server,job['template_snapshot'],batch.child_spec(job,index),compiler_check=True)
                    self.assertEqual(outputs,['4'])
            self.assertEqual(len(calls),3)
            self.assertTrue(all(call[2] for call in calls))
        asyncio.run(scenario())

    def test_server_runner_failure_resume_and_restart(self):
        async def scenario():
            job=self.prepare()
            class Queue:
                def __init__(self):self.pending=[];self.history={};self.failed=False;self.seen=[]
                def get_current_queue(self):return [],self.pending
                def get_history(self,prompt_id):return {prompt_id:self.history[prompt_id]} if prompt_id in self.history else {}
                def put(self,row):
                    self.pending.append(row)
                    asyncio.create_task(self.execute(row))
                async def execute(self,row):
                    spec=json.loads(row[2]['1']['inputs']['request']);self.seen.append(spec['batch_index'])
                    if spec['batch_index']==1 and not self.failed:
                        self.failed=True
                        self.history[row[1]]={'status':{'messages':[['execution_error',{'exception_message':'Test failure'}]]}}
                    else:
                        parts=video(frames=spec['visible_frames']).get_components()
                        await asyncio.to_thread(editor.PlaylistRedoSave().save,parts.images,json.dumps(spec),audio=parts.audio)
                    self.pending.remove(row)
                def delete_queue_item(self,fn):self.pending=[r for r in self.pending if not fn(r)]
            queue=Queue();server=types.SimpleNamespace(prompt_queue=queue,number=0)
            async def check(server,template,spec,compiler_check=False):return editor.redo_graph(template,spec),['4']
            with patch.object(batch,'checked_graph',check):
                await batch.start_batch(server,self.token,job['id'])
                await batch._TASKS[(self.token,job['id'])]
                stopped=batch.batch_job(self.token,job['id'])
                self.assertEqual(stopped['state'],'failed')
                self.assertEqual(queue.seen,[0,1])
                first=disk.playlist_manifest(self.token)[1]['clips'][-1]
                digest=hashlib.sha256(disk.playlist_media(self.token,first['clip_id']).read_bytes()).hexdigest()
                await asyncio.sleep(0)
                await batch.start_batch(server,self.token,job['id'],resume=True)
                await batch._TASKS[(self.token,job['id'])]
                self.assertEqual(batch.batch_job(self.token,job['id'])['state'],'completed')
                self.assertEqual(queue.seen,[0,1,1,2])
                self.assertEqual(hashlib.sha256(disk.playlist_media(self.token,first['clip_id']).read_bytes()).hexdigest(),digest)
                self.doc=disk.playlist_manifest(self.token)[1]
                interrupted=self.prepare()
                batch.set_batch(self.token,interrupted['id'],state='running')
                batch.reconcile_batches(self.token,server)
                self.assertEqual(batch.batch_job(self.token,interrupted['id'])['state'],'failed')
                self.assertEqual(queue.seen,[0,1,1,2])
        asyncio.run(scenario())

    def test_preflight_fails_before_queue_and_cancellation(self):
        async def scenario():
            job=self.prepare()
            queue=types.SimpleNamespace(get_current_queue=lambda:([],[]),get_history=lambda **kw:{},delete_queue_item=lambda fn:None)
            server=types.SimpleNamespace(prompt_queue=queue)
            async def reject(server,template,spec,compiler_check=False):
                if spec['batch_index']==2:raise ValueError('Invalid reference')
                return {},[]
            with patch.object(batch,'checked_graph',reject):
                await batch.start_batch(server,self.token,job['id'])
                await batch._TASKS[(self.token,job['id'])]
            saved=batch.batch_job(self.token,job['id'])
            self.assertEqual(saved['children'],[])
            self.assertIn('Prompt 3',saved['error'])
            batch.cancel_batch(server,self.token,job['id'])
            self.assertEqual(batch.batch_job(self.token,job['id'])['state'],'canceled')
        asyncio.run(scenario())


if __name__=='__main__':unittest.main()
