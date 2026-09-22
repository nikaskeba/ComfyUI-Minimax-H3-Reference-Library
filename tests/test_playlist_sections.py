"""Section redo: exact context windows, disk stitching and adoption."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import av
import torch
import test_playlist_editor as base
from comfy_api.latest import InputImpl, Types
editor, disk = base.editor, base.disk
from test_disk_video import video, inspect


class SectionTests(unittest.TestCase):
    setUp = base.PlaylistEditorTests.setUp
    payload = base.PlaylistEditorTests.payload
    # Reuse the fixture without rerunning the whole-clip test methods here.
    def source(self, fps=24):
        clip=self.doc['clips'][1]
        path=self.directory/clip['filename']
        images=torch.zeros(12*fps,48,64,3)
        images[:4*fps,...,0]=1;images[4*fps:8*fps,...,1]=1;images[8*fps:,...,2]=1
        waveform=torch.sin(torch.arange(12*48000)*440*2*torch.pi/48000)*.1
        disk._write_clip(InputImpl.VideoFromComponents(Types.VideoComponents(images=images,frame_rate=fps,
                         audio={'waveform':waveform[None,None],'sample_rate':48000})),path)
        clip.update(disk._clip_metadata(path))
        disk.write_project(self.directory,self.doc)
        return path

    def request(self,mode='replace',start=4,end=8,duration=2,**kwargs):
        _,doc=disk.playlist_manifest(self.token)
        payload=self.payload(revision=doc['revision'],edit={'mode':mode,'start':start,'end':end},duration=duration,**kwargs)
        result=editor.prepare_redo(self.token,payload)
        return result['graph']['1']['inputs']['request']

    def generated(self,seconds=2):
        frames=round(seconds*24)
        images=torch.zeros(frames,48,64,3);images[...,:2]=1
        audio=torch.sin(torch.arange(round(seconds*48000))*880*2*torch.pi/48000)*.1
        return images,{'waveform':audio[None,None],'sample_rate':48000}

    def save(self,request):
        spec=json.loads(request);images,audio=self.generated(spec['duration'])
        return editor.PlaylistRedoSave().save(images,request,audio=audio)['result'][0]

    def test_internal_and_boundary_context_windows(self):
        self.source()
        spec=json.loads(self.request())
        self.assertAlmostEqual(spec['neighbors']['previous']['start_seconds'],4-22/24)
        self.assertEqual(spec['neighbors']['next']['start_seconds'],8)
        for side,channel in [('previous',0),('next',2)]:
            images,audio=editor.neighbor_media(spec,side)
            self.assertEqual(len(images),22);self.assertGreater(float(images[...,channel].mean()),.85)
        spec=json.loads(self.request(start=0,end=5))
        self.assertEqual(spec['neighbors']['previous']['clip_id'],self.doc['clips'][0]['clip_id'])
        self.assertEqual(spec['neighbors']['next']['start_seconds'],5)
        spec=json.loads(self.request(start=0,end=5,previous={'enabled':False}))
        self.assertEqual(set(spec['neighbors']),{'next'})
        spec=json.loads(self.request(start=8,end=12))
        self.assertEqual(spec['neighbors']['next']['clip_id'],self.doc['clips'][2]['clip_id'])
        spec=json.loads(self.request(start=.125,end=11.75))
        self.assertNotIn('previous',spec['neighbors']);self.assertEqual(spec['neighbors']['next']['frames'],5)
        spec=json.loads(self.request(start=.5,end=8))
        self.assertEqual(spec['neighbors']['previous']['frames'],5)

    def test_assembly_pixels_audio_and_original_unchanged(self):
        source=self.source();digest=hashlib.sha256(source.read_bytes()).digest()
        request=self.request();identifier=self.save(request)
        _,doc=disk.playlist_manifest(self.token);out=disk.playlist_media(self.token,identifier)
        self.assertEqual(doc['timeline'],self.doc['timeline']);self.assertEqual(len(doc['clips']),5)
        self.assertEqual(inspect(out)[0],240)
        with av.open(str(out)) as container:frames=[f.to_ndarray(format='rgb24').mean(axis=(0,1)) for f in container.decode(video=0)]
        for index,expected in [(95,(1,0,0)),(96,(1,1,0)),(143,(1,1,0)),(144,(0,0,1))]:
            for channel,value in enumerate(expected):self.assertAlmostEqual(float(frames[index][channel])/255,value,delta=.08)
        waveform,rate=editor.load_audio(str(out))
        for second,freq in [(1,440),(4.5,880),(7,440)]:
            part=waveform[0,int(second*rate):int((second+.2)*rate)]
            peak=int(torch.fft.rfft(part).abs().argmax())*rate/len(part)
            self.assertAlmostEqual(peak,freq,delta=6)
        self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),digest)
        applied=editor.edit_timeline(self.token,{'revision':doc['revision'],'action':'adopt','clip_id':identifier})
        self.assertEqual(applied['timeline'][1]['clip_id'],identifier)
        with self.assertRaisesRegex(ValueError,'occurrence changed'):
            editor.edit_timeline(self.token,{'revision':applied['revision'],'action':'adopt','clip_id':identifier})
        restored=editor.edit_timeline(self.token,{'revision':applied['revision'],'action':'undo'})
        self.assertEqual(restored['timeline'],self.doc['timeline'])

    def test_insertion_with_zero_or_five_seconds_cut_and_fps_conversion(self):
        self.source(fps=25)
        for start,end,seconds in [(4,4,2),(4,9,2),(0,5,1),(8,12,5),(0,12,2)]:
            with self.subTest(start=start,end=end,seconds=seconds):
                request=self.request(mode='insert',start=start,end=end,duration=seconds)
                identifier=self.save(request)
                metadata=disk._clip_metadata(disk.playlist_media(self.token,identifier))
                self.assertEqual(metadata['frame_count'],round((12-(end-start)+seconds)*25))
                self.assertEqual(metadata['fps'],25)
                self.assertEqual((metadata['width'],metadata['height']),(64,48))

    def test_between_clips_and_stale_adoption(self):
        self.source()
        identifier=self.save(self.request(mode='insert_between',start=0,end=0))
        _,doc=disk.playlist_manifest(self.token)
        applied=editor.edit_timeline(self.token,{'revision':doc['revision'],'action':'adopt','clip_id':identifier})
        self.assertEqual([e['clip_id'] for e in applied['timeline']],
                         [self.doc['clips'][0]['clip_id'],self.doc['clips'][1]['clip_id'],identifier,self.doc['clips'][2]['clip_id']])
        with self.assertRaisesRegex(ValueError,'boundary changed'):
            editor.edit_timeline(self.token,{'revision':applied['revision'],'action':'adopt','clip_id':identifier})

    def test_failed_or_canceled_assembly_publishes_nothing(self):
        self.source();request=self.request();_,before=disk.playlist_manifest(self.token)
        with patch.object(editor,'assemble_section',side_effect=RuntimeError('assembly failed')):
            with self.assertRaisesRegex(RuntimeError,'assembly failed'):self.save(request)
        _,after=disk.playlist_manifest(self.token)
        self.assertEqual(after['clips'],before['clips'])
        spec=json.loads(request);editor.update_job(self.token,spec['request_id'],{'state':'canceled'})
        with self.assertRaisesRegex(ValueError,'canceled'):self.save(request)
        self.assertFalse(list(self.directory.glob('redo_*.mp4')))


if __name__=='__main__':unittest.main()
