"""Create playlist projects and normalize uploaded media without loading frames into RAM."""
from pathlib import Path
import re
import subprocess
import uuid

import av
import folder_paths
from .disk_video import (_MANIFEST_LOCK, _ffmpeg, _clip_metadata, normalize_project,
                         write_project, register_playlist, playlist_manifest)


def create_project(name):
    name = str(name or "").strip()
    if not name or len(name) > 100:
        raise ValueError("Enter a project name between 1 and 100 characters.")
    folder = re.sub(r'[^\w .-]', '_', name).strip(' .') or 'project'
    directory = Path(folder_paths.get_output_directory()).resolve() / 'h3_projects' / (folder + '_' + uuid.uuid4().hex[:8])
    with _MANIFEST_LOCK:
        directory.mkdir(parents=True, exist_ok=False)
        write_project(directory, normalize_project({'name':name, 'clips':[], 'combined_videos':[]}))
        token = register_playlist(directory)
    return {'id':token, 'name':name}


def import_video(token, source, original_name):
    directory, _ = playlist_manifest(token)
    output = directory / ('import_' + uuid.uuid4().hex + '.mp4')
    try:
        with av.open(str(source)) as container:
            if not container.streams.video:
                raise ValueError("The selected file contains no video track.")
            stream = container.streams.video[0]
            fps = stream.average_rate or stream.guessed_rate
            if not fps or fps <= 0:
                raise ValueError("Could not determine this video's frame rate.")
            has_audio = bool(container.streams.audio)
        command = [_ffmpeg(), '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source)]
        if not has_audio:
            command += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
        command += ['-map', '0:v:0', '-map', '0:a:0' if has_audio else '1:a:0',
                    '-vf', f'fps={fps},scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1',
                    '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p',
                    '-af', 'aresample=48000,apad', '-ac', '2', '-c:a', 'aac', '-b:a', '192k',
                    '-shortest', '-movflags', '+faststart', str(output)]
        result = subprocess.run(command, capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('Video import failed: ' + result.stderr.decode('utf8', errors='replace')[-2000:])
        metadata = _clip_metadata(output)
        if metadata['frame_count'] <= 0:
            raise ValueError('The video has no decodable frames.')
        with _MANIFEST_LOCK:
            directory, doc = playlist_manifest(token)
            clip = {**metadata, 'clip_id':output.stem, 'index':len(doc['clips'])+1,
                    'prompt':'', 'source_filename':original_name, 'media_role':'imported'}
            doc['clips'].append(clip)
            doc['undo'].append(list(doc['timeline']))
            doc['undo'] = doc['undo'][-100:]
            doc['redo'] = []
            doc['timeline'].append({'id':uuid.uuid4().hex, 'clip_id':output.stem})
            doc['revision'] += 1
            write_project(directory, doc)
        return clip
    except BaseException:
        output.unlink(missing_ok=True)
        raise
