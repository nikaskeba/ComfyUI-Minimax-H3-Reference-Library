import copy
import importlib
import unittest
import test_playlist_editor as base

registration=importlib.import_module('playlist_test_package.playlist_registration')


class RegistrationTests(unittest.TestCase):
    setUp=base.PlaylistEditorTests.setUp

    def main_graph(self):
        graph=base.template_graph()
        graph.pop('1');graph.pop('4');graph.pop('5')
        graph['register']={'class_type':'SkebaPlaylistWorkflow','inputs':{'images':['decode',0],'audio':['decode_audio',0],'upscale_connector':['3',1],'crf':0}}
        graph['decode']={'class_type':'VAEDecode','inputs':{'samples':['9',0]}}
        graph['decode_audio']={'class_type':'VAEDecodeAudio','inputs':{'samples':['9',0]}}
        graph['9']['inputs']['positive']=['motion',0]
        graph['motion']={'class_type':'SKEBAMiniMaxH3MotionContext','inputs':{'conditioning':['3',0],'context_latent':['old',0]}}
        graph['old']={'class_type':'SKEBAMiniMaxH3MotionContextLoadLatent','inputs':{}}
        for key in ('7','8'):
            graph[key]['inputs']['length']=['loop',0]
            graph[key]['inputs']['first_frame']=['old',0]
        graph['6']['inputs']['prompt_template']=['loop',0]
        graph['10']['inputs']['noise_seed']=['loop',0]
        graph['loop']={'class_type':'ForLoopOpen | akatz-loops','inputs':{}}
        # Avoid the simplified fixture's feedback edge.
        graph['8']['inputs'].pop('target_latent',None)
        return graph

    def test_extract_does_not_mutate_main_and_updates_same_template(self):
        graph=self.main_graph();original=copy.deepcopy(graph)
        extracted=registration.extract_renderer(graph,'register')
        self.assertEqual(graph,original)
        self.assertNotIn('loop',extracted);self.assertNotIn('old',extracted);self.assertNotIn('motion',extracted)
        self.assertEqual(extracted['9']['inputs']['positive'],['3',0])
        self.assertTrue(extracted['3']['inputs']['preserve_upscaled_endpoints'])
        for key in ('7','8'):self.assertNotIn('first_frame',extracted[key]['inputs'])
        saved=base.editor.register_template('Main',extracted)
        updated=base.editor.register_template('Main updated',extracted,saved['id'])
        self.assertEqual(saved['id'],updated['id'])
        self.assertEqual(base.editor.read_template(saved['id'])['graph']['playlist_register_save']['inputs']['crf'],0)
        self.assertFalse(getattr(registration.PlaylistWorkflow,'OUTPUT_NODE',False))

    def test_unresolved_batch_dependency_rejected(self):
        graph=self.main_graph();graph['9']['inputs']['unexpected']=['loop',0]
        with self.assertRaisesRegex(ValueError,'Unresolved batch dependencies'):
            registration.extract_renderer(graph,'register')

    def test_named_getters_resolve_and_ambiguous_names_fail(self):
        graph=self.main_graph()
        graph['setter']={'class_type':'Setter','inputs':{'key':'shared_conditioning','value':['3',0]}}
        graph['getter']={'class_type':'Getter','inputs':{'key':'shared_conditioning'}}
        graph['motion']['inputs']['conditioning']=['getter',0]
        extracted=registration.extract_renderer(graph,'register')
        self.assertEqual(extracted['9']['inputs']['positive'],['3',0])
        self.assertNotIn('getter',extracted)
        graph['duplicate']=copy.deepcopy(graph['setter'])
        with self.assertRaisesRegex(ValueError,'unambiguous Setter'):
            registration.extract_renderer(graph,'register')

    def test_reference_fps_preserved_as_float_and_old_templates_repaired(self):
        graph=self.main_graph()
        graph['fps']={'class_type':'PrimitiveInt','inputs':{'value':24}}
        graph['6']['inputs']['video_fps']=['fps',0]
        extracted=registration.extract_renderer(graph,'register')
        self.assertEqual(extracted['6']['inputs']['video_fps'],24.0)
        self.assertIs(type(extracted['6']['inputs']['video_fps']),float)
        # Simulate an already-registered snapshot that still has the old link.
        extracted['6']['inputs']['video_fps']=['fps',0]
        saved=base.editor.register_template('Legacy',extracted)
        result=base.editor.prepare_redo(self.token,{'revision':self.doc['revision'],'entry_id':self.doc['timeline'][1]['id'],'template':saved['id'],'prompt':'A test shot','duration':3})
        self.assertIs(type(result['graph']['6']['inputs']['video_fps']),float)
        self.assertEqual(base.editor.read_template(saved['id'])['graph']['6']['inputs']['video_fps'],['fps',0])
