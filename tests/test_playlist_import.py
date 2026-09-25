"""External video import into new, empty projects."""
import importlib
import unittest
import subprocess
import av
from pathlib import Path
import test_playlist_editor as base

imports = importlib.import_module('playlist_test_package.playlist_import')


class ImportTests(unittest.TestCase):
    setUp = base.PlaylistEditorTests.setUp

    def test_project_summary_and_delete(self):
        project = imports.create_project('Disposable')
        directory, _ = base.disk.playlist_manifest(project['id'])
        summaries = base.disk.project_summaries()
        summary = next(item for item in summaries if item['id'] == project['id'])
        self.assertEqual(summary['clip_count'], 0)
        self.assertEqual(summary['duration_seconds'], 0)
        self.assertGreater(summary['updated_at'], 0)
        source = base.disk.playlist_media(self.token, self.doc['clips'][0]['clip_id'])
        original = source.read_bytes()
        imports.import_video(project['id'], source, 'original.mp4')
        summary = next(item for item in base.disk.project_summaries() if item['id'] == project['id'])
        self.assertEqual(summary['clip_count'], 1)
        self.assertAlmostEqual(summary['duration_seconds'], 3)
        base.disk.delete_project(project['id'])
        self.assertFalse(directory.exists())
        self.assertNotIn(project['id'], base.disk.playlist_projects())
        self.assertEqual(source.read_bytes(), original)

    def test_delete_rejects_active_jobs_and_unsafe_folder(self):
        project = imports.create_project('Busy')
        directory, doc = base.disk.playlist_manifest(project['id'])
        doc['jobs'] = [{'state': 'queued'}]
        base.disk.write_project(directory, doc)
        with self.assertRaisesRegex(ValueError, 'generation jobs'):
            base.disk.delete_project(project['id'])
        self.assertTrue(directory.exists())
        outside = Path(self.temp.name) / 'outside_project'
        outside.mkdir()
        base.disk.write_project(outside, {'clips': []})
        token = base.disk.register_playlist(outside)
        with self.assertRaisesRegex(ValueError, 'output directory'):
            base.disk.delete_project(token)
        self.assertTrue(outside.exists())

    def test_blank_project_import_and_undo(self):
        project = imports.create_project('Outside videos')
        directory, doc = base.disk.playlist_manifest(project['id'])
        self.assertEqual(doc['clips'], [])
        self.assertEqual(doc['timeline'], [])
        source = base.disk.playlist_media(self.token, self.doc['clips'][0]['clip_id'])
        original = source.read_bytes()
        clip = imports.import_video(project['id'], source, 'holiday.mov')
        self.assertEqual(clip['prompt'], '')
        self.assertEqual(clip['source_filename'], 'holiday.mov')
        self.assertEqual(clip['frame_count'], 72)
        self.assertEqual(source.read_bytes(), original)
        _, doc = base.disk.playlist_manifest(project['id'])
        self.assertEqual(doc['timeline'][0]['clip_id'], clip['clip_id'])
        undone = base.editor.edit_timeline(project['id'], {'revision':doc['revision'], 'action':'undo'})
        self.assertEqual(undone['timeline'], [])
        self.assertTrue(base.disk.playlist_media(project['id'], clip['clip_id']).exists())

    def test_invalid_import_does_not_publish(self):
        project = imports.create_project('../Safe project')
        directory, doc = base.disk.playlist_manifest(project['id'])
        self.assertTrue(directory.is_relative_to(Path(base.disk.folder_paths.get_output_directory()).resolve()))
        source = Path(self.temp.name)/'invalid';source.write_bytes(b'not video')
        with self.assertRaises(Exception):
            imports.import_video(project['id'], source, 'bad.mp4')
        self.assertEqual(base.disk.playlist_manifest(project['id'])[1]['clips'], [])
        self.assertEqual(list(directory.glob('*.mp4')), [])

    def test_silent_video_gets_editable_audio_track(self):
        project = imports.create_project('Silent footage')
        source = base.disk.playlist_media(self.token, self.doc['clips'][0]['clip_id'])
        silent = Path(self.temp.name)/'silent.mkv'
        subprocess.run([base.disk._ffmpeg(), '-v', 'error', '-i', str(source), '-an', '-c:v', 'copy', str(silent)], check=True)
        clip = imports.import_video(project['id'], silent, 'silent.mkv')
        with av.open(str(base.disk.playlist_media(project['id'], clip['clip_id']))) as container:
            self.assertEqual(len(container.streams.audio), 1)
            self.assertEqual(container.streams.audio[0].rate, 48000)
        self.assertEqual(clip['frame_count'], 72)
