"""Frame-accurate section edits and disk-based assembly for playlist redo."""
import copy
import subprocess
from fractions import Fraction

import av
import comfy.model_management
from .playlist_timeline import frame_range
from .disk_video import _ffmpeg, playlist_media


def section_edit(doc, index, payload):
    choice = payload.get('edit')
    if not choice:
        return None
    mode = choice.get('mode')
    if mode not in ('replace', 'insert', 'insert_between'):
        raise ValueError('Unknown section edit mode.')
    entry = doc['timeline'][index]
    source = next(c for c in doc['clips'] if c['clip_id'] == entry['clip_id'])
    fps = float(source['fps'])
    source_start, source_end = frame_range(entry, source)
    count = source_end-source_start
    start = round(float(choice.get('start', 0)) * fps)
    end = round(float(choice.get('end', count / fps if mode == 'replace' else start/fps)) * fps) if mode != 'insert_between' else start
    if not 0 <= start <= end <= count or (mode == 'replace' and start == end):
        raise ValueError('Choose a nonempty replacement range or an insertion point inside the clip.')
    result = {'mode':mode, 'source_entry':copy.deepcopy(entry), 'start_frame':source_start+start,
              'end_frame':source_start+end, 'source_frames':source_end, 'source_start':source_start, 'fps':source.get('fps_fraction', str(fps)),
              'width':source['width'], 'height':source['height']}
    if mode == 'insert_between':
        boundary = index + (0 if choice.get('side') == 'before' else 1)
        result['boundary'] = {'left':copy.deepcopy(doc['timeline'][boundary-1]) if boundary else None,
                              'right':copy.deepcopy(doc['timeline'][boundary]) if boundary < len(doc['timeline']) else None}
    return result


def context_window(doc, index, side, edit):
    clips = {c['clip_id']:c for c in doc['clips']}
    timeline = doc['timeline']
    current = clips[timeline[index]['clip_id']]
    if edit and edit['mode'] == 'insert_between':
        entry = edit['boundary']['left' if side == 'previous' else 'right']
        clip = clips[entry['clip_id']] if entry else None
        return (clip, frame_range(entry,clip)[0]/clip['fps'], frame_range(entry,clip)[1]/clip['fps']) if clip else None
    source_start, source_end = frame_range(timeline[index], current)
    low, high = source_start/current['fps'], source_end/current['fps']
    if edit:
        fps = float(Fraction(edit['fps']))
        start, end = edit['start_frame']/fps, edit['end_frame']/fps
        if side == 'previous' and start > low:
            return current, low, start
        if side == 'next' and end < high - 1e-7:
            return current, end, high
    other = index + (-1 if side == 'previous' else 1)
    if not 0 <= other < len(timeline):
        return None
    clip = clips[timeline[other]['clip_id']]
    start,end=frame_range(timeline[other],clip)
    return clip,start/clip['fps'],end/clip['fps']


def adopt_timeline(doc, clip_id):
    clip = next((c for c in doc['clips'] if c['clip_id'] == clip_id), None)
    if not clip or clip.get('media_role') == 'generated_section':
        raise ValueError('Choose a completed alternate.')
    edit = clip.get('redo', {}).get('edit')
    if not edit:
        raise ValueError('This clip has no saved edit position. Insert it manually.')
    timeline = copy.deepcopy(doc['timeline'])
    if edit['mode'] == 'insert_between':
        boundary = edit['boundary']
        positions = [i for i in range(len(timeline)+1)
                     if (timeline[i-1] if i else None) == boundary['left']
                     and (timeline[i] if i < len(timeline) else None) == boundary['right']]
        if not positions:
            raise ValueError('The insertion boundary changed. Insert the clip manually.')
        import_id = clip['clip_id'] + '_' + str(doc['revision'])
        timeline.insert(positions[0], {'id':import_id, 'clip_id':clip_id})
    else:
        index = next((i for i,e in enumerate(timeline) if e == edit['source_entry']), None)
        if index is None:
            raise ValueError('The original timeline occurrence changed. Insert the alternate manually.')
        timeline[index] = {'id':timeline[index]['id'], 'clip_id':clip_id}
    return timeline


def run_ffmpeg(command, output):
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        while True:
            comfy.model_management.throw_exception_if_processing_interrupted()
            try:
                _, stderr = process.communicate(timeout=.25)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode:
            raise RuntimeError('Section assembly failed: ' + stderr.decode('utf-8', errors='replace'))
    except BaseException:
        if process.poll() is None:
            process.terminate()
        process.communicate()
        output.unlink(missing_ok=True)
        raise


def assemble_section(spec, section_path, output, crf):
    edit = spec['edit']
    fps = Fraction(edit['fps'])
    generated_count = max(1, round(spec['duration'] * float(fps)))
    source = playlist_media(spec['project'], spec['parent_clip_id'])
    pieces = []
    if edit['mode'] != 'insert_between' and edit['start_frame'] > edit.get('source_start',0):
        pieces.append((source, edit.get('source_start',0), edit['start_frame'], False))
    pieces.append((section_path, 0, generated_count, True))
    if edit['mode'] != 'insert_between' and edit['end_frame'] < edit['source_frames']:
        pieces.append((source, edit['end_frame'], edit['source_frames'], False))
    command = [_ffmpeg(), '-hide_banner', '-loglevel', 'error', '-y']
    filters = []
    for i,(path,start,end,generated) in enumerate(pieces):
        command += ['-i',str(path)]
        duration = (end-start)/float(fps)
        if generated:
            video = (f'fps={fps},scale={edit["width"]}:{edit["height"]}:force_original_aspect_ratio=decrease,'
                     f'pad={edit["width"]}:{edit["height"]}:(ow-iw)/2:(oh-ih)/2,'
                     f'tpad=stop_mode=clone:stop_duration=1,trim=end_frame={end}')
        else:
            video = f'trim=start_frame={start}:end_frame={end}'
        filters.append(f'[{i}:v]{video},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v{i}]')
        with av.open(str(path)) as container:
            has_audio = bool(container.streams.audio)
        samples = round(duration*48000)
        if has_audio:
            begin = 0 if generated else round(start/float(fps)*48000)
            audio = (f'[{i}:a]aresample=48000,aformat=channel_layouts=stereo,'
                     f'atrim=start_sample={begin}:end_sample={begin+samples},asetpts=PTS-STARTPTS,'
                     f'apad=whole_len={samples},atrim=end_sample={samples}')
        else:
            audio = f'anullsrc=r=48000:cl=stereo,atrim=end_sample={samples}'
        filters.append(audio+f'[a{i}]')
    filters.append(''.join(f'[v{i}][a{i}]' for i in range(len(pieces)))+f'concat=n={len(pieces)}:v=1:a=1[v][a]')
    command += ['-filter_complex',';'.join(filters),'-map','[v]','-map','[a]',
                '-r',str(fps),'-c:v','libx264','-crf',str(crf),'-pix_fmt','yuv420p',
                '-c:a','aac','-b:a','192k','-movflags','+faststart',str(output)]
    run_ffmpeg(command, output)
    return sum(end-start for _,start,end,_ in pieces)
