"""Nondestructive, frame-based timeline ranges."""
import subprocess
from fractions import Fraction


def frame_range(entry, clip):
    start, end = entry.get('in_frame', 0), entry.get('out_frame', clip['frame_count'])
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= clip['frame_count']:
        raise ValueError('Timeline trim must retain at least one frame within the source clip.')
    return start, end


def clean_entry(entry, clip):
    start, end = frame_range(entry, clip)
    result = {'id':entry['id'], 'clip_id':entry['clip_id']}
    if start or end != clip['frame_count']:
        result.update(in_frame=start, out_frame=end)
    return result


def render_timeline(ffmpeg, pieces, output):
    first = pieces[0][1]
    fps = Fraction(first['fps_fraction'])
    width, height = first['width'], first['height']
    command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y']
    filters = []
    for i, (path, clip, entry) in enumerate(pieces):
        command += ['-i', str(path)]
        start, end = frame_range(entry, clip)
        source_fps = float(Fraction(clip['fps_fraction']))
        duration = (end-start)/source_fps
        frames = max(1, round(duration*float(fps)))
        samples = round(frames/float(fps)*48000)
        filters.append(f'[{i}:v]trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS,'
                       f'fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,'
                       f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,'
                       f'tpad=stop_mode=clone:stop_duration=1,trim=end_frame={frames}[v{i}]')
        begin=round(start/source_fps*48000)
        filters.append(f'[{i}:a]aresample=48000,aformat=channel_layouts=stereo,'
                       f'atrim=start_sample={begin}:end_sample={round(end/source_fps*48000)},'
                       f'asetpts=PTS-STARTPTS,apad=whole_len={samples},atrim=end_sample={samples}[a{i}]')
    filters.append(''.join(f'[v{i}][a{i}]' for i in range(len(pieces)))+f'concat=n={len(pieces)}:v=1:a=1[v][a]')
    command += ['-filter_complex',';'.join(filters),'-map','[v]','-map','[a]',
                '-r',str(fps),'-c:v','libx264','-crf','18','-pix_fmt','yuv420p',
                '-c:a','aac','-b:a','192k','-movflags','+faststart',str(output)]
    try:
        result=subprocess.run(command,capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:
            raise RuntimeError('Timeline export failed: '+result.stderr.decode('utf8',errors='replace'))
    except BaseException:
        output.unlink(missing_ok=True)
        raise
