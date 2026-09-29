"""Persistent, sequential playlist generation; only active task handles live in memory."""
import asyncio
import copy
import inspect
import json
import re
import uuid

import comfy.model_management

from .disk_video import _MANIFEST_LOCK, playlist_manifest, playlist_media, write_project, _clip_metadata
from .playlist_editor import (prepare_redo, read_template, redo_graph, timing, generation_prompt,
                              reconcile_jobs, RevisionConflict)
from .playlist_sections import section_edit, assemble_section, assemble_generated

_TASKS = {}
_SESSION = uuid.uuid4().hex


def prompt_segments(text, default_duration=15):
    parts = text.split('|')
    result = []
    timing(default_duration)
    for index, prompt in enumerate(parts, 1):
        if not prompt.strip():
            raise ValueError(f'Prompt {index} is empty. Remove the extra | or enter a prompt.')
        matches = re.findall(r'\[s\s*=\s*([^\]]*)\]', prompt, re.I)
        if len(matches) > 1:
            raise ValueError(f'Prompt {index}: use one [s=x] duration.')
        try:
            visible, _ = timing(matches[0] if matches else default_duration)
        except (ValueError, TypeError):
            raise ValueError(f'Prompt {index}: duration must be a positive number.') from None
        result.append({'prompt':prompt, 'duration':visible/24,
                       'scene_change':bool(re.search(r'\[new_location\]', prompt, re.I))})
    return result


def prepare_batch(token, payload):
    segments = prompt_segments(payload.get('prompt',''), payload.get('batch_default_duration',15))
    continuation = payload.get('continuation') or {}
    frames = int(continuation.get('frames',22))
    if frames not in (5,22,39,56):
        raise ValueError('Batch context frames must be 5, 22, 39 or 56.')
    template = read_template(payload.get('template'))
    # Capture original external windows once, before generated clips alter the project.
    prepared = prepare_redo(token, {**payload,'prompt':segments[0]['prompt'],
                                   'duration':segments[0]['duration']}, template=template, persist=False)
    with _MANIFEST_LOCK:
        directory, doc = playlist_manifest(token)
        if doc['revision'] != payload['revision']:
            raise RevisionConflict('Timeline changed. Reopen Edit Clip.')
        index = next(i for i,e in enumerate(doc['timeline']) if e['id']==payload['entry_id'])
        source = next(c for c in doc['clips'] if c['clip_id']==prepared['spec']['parent_clip_id'])
        base = prepared['spec']
        # Whole-clip batches also get occurrence-safe, undoable adoption.
        if 'edit' not in base:
            base['edit'] = section_edit(doc,index,{'edit':{'mode':'replace'}})
        base['geometry'] = {'width':source['width'],'height':source['height']}
        base['duration'] = sum(s['duration'] for s in segments)
        base['prompt'] = payload['prompt']
        identifier = uuid.uuid4().hex
        base['request_id'] = identifier
        job = {'id':identifier, 'state':'prepared', 'kind':'batch', 'spec':base,
               'segments':segments, 'template_snapshot':template, 'children':[], 'runner_session':_SESSION,
               'continuation':{'enabled':bool(continuation.get('enabled',True)),
                               'frames':frames,'audio':bool(continuation.get('audio',True))}}
        doc['jobs'].append(job)
        doc['redo_template'] = payload['template']
        write_project(directory,doc)
    return job


def batch_job(token, identifier):
    _,doc = playlist_manifest(token)
    job = next((j for j in doc['jobs'] if j['id']==identifier and j.get('kind')=='batch'),None)
    if not job:
        raise ValueError('Unknown playlist batch.')
    return job


def set_batch(token, identifier, **changes):
    with _MANIFEST_LOCK:
        directory,doc = playlist_manifest(token)
        job = next(j for j in doc['jobs'] if j['id']==identifier)
        if job['state']=='completed':
            return job
        if job['state']=='canceled' and changes.get('state')!='running':
            return job
        job.update(changes)
        write_project(directory,doc)
        return job


def retry_job(server, token, identifier, prompt):
    if not isinstance(prompt,str) or not prompt.strip():raise ValueError('Enter a prompt to retry.')
    with _MANIFEST_LOCK:
        directory,doc = reconcile_jobs(token,server.prompt_queue)
        old = next((j for j in doc['jobs'] if j['id']==identifier),None)
        if not old or old['state'] not in ('failed','canceled','completed'):
            raise ValueError('Wait for the job to finish or cancel it before retrying.')
        if (token,identifier) in _TASKS:
            raise ValueError('The batch is still stopping. Retry in a moment.')
        running,pending=server.prompt_queue.get_current_queue()
        active={row[1] for row in running+pending}
        related={identifier,*old.get('children',[])}
        if any(j.get('prompt_id') in active for j in doc['jobs'] if j['id'] in related):
            raise ValueError('A clip is still queued or running. Wait before retrying.')
        spec=copy.deepcopy(old['spec'])
        playlist_media(token,spec['parent_clip_id'])
        for neighbor in spec['neighbors'].values():playlist_media(token,neighbor['clip_id'])
        spec.update(request_id=uuid.uuid4().hex,prompt=prompt)
        template=copy.deepcopy(old.get('template_snapshot') or read_template(spec['template']))
        job={'id':spec['request_id'],'state':'prepared','spec':spec,'template_snapshot':template,'retry_of':identifier}
        if old.get('kind')=='batch':
            parts=prompt.split('|')
            if len(parts)!=len(old['segments']):raise ValueError('Keep the same number of prompts when retrying a batch.')
            segments=[prompt_segments(part,original['duration'])[0] for part,original in zip(parts,old['segments'])]
            children=[]
            if old['state']!='completed':
                known={j['id']:j for j in doc['jobs']}
                for index,child in enumerate(old['children']):
                    if known[child]['state']!='completed':break
                    if segments[index]!=old['segments'][index]:
                        raise ValueError(f'Prompt {index+1} already completed. Edit its clip separately; retry changes only unfinished prompts.')
                    playlist_media(token,known[child]['clip_id'])
                    children.append(child)
            spec['duration']=sum(s['duration'] for s in segments)
            job.update(kind='batch',segments=segments,children=children,continuation=copy.deepcopy(old['continuation']),runner_session=_SESSION)
            result={'batch_id':job['id'],'managed':True}
        else:
            if '|' in prompt:raise ValueError('Retry this single clip with one prompt. Use Edit Clip to create a batch.')
            duration=prompt_segments(prompt,spec['duration'])[0]['duration']
            visible,generation=timing(duration,*[spec['neighbors'].get(side,{}).get('frames',0) for side in ('previous','next')])
            spec.update(duration=duration,visible_frames=visible,generation_length=generation)
            job.update(prompt_id=str(uuid.uuid4()),output_node=template['output'])
            result={'request_id':job['id'],'prompt_id':job['prompt_id'],'graph':redo_graph(template,spec)}
        doc['jobs'].append(job)
        write_project(directory,doc)
        return result


def child_spec(job, index, previous=None):
    segment = job['segments'][index]
    spec = copy.deepcopy(job['spec'])
    spec.pop('edit',None)
    spec.update(request_id=uuid.uuid4().hex,batch_id=job['id'],batch_index=index,
                prompt=segment['prompt'],neighbors={})
    external = job['spec']['neighbors']
    if index == 0 and external.get('previous'):
        spec['neighbors']['previous'] = copy.deepcopy(external['previous'])
    elif index and job['continuation']['enabled'] and not segment['scene_change']:
        available = previous['duration_seconds'] if previous else job['segments'][index-1]['duration']
        fits = [n for n in (5,22,39,56) if n<=job['continuation']['frames'] and n/24<=available+1e-7]
        if fits:
            count = max(fits)
            spec['neighbors']['previous'] = {'clip_id':previous['clip_id'] if previous else '__batch_previous__',
                'frames':count,'audio':job['continuation']['audio'] and (previous.get('has_audio',True) if previous else True),
                'start_seconds':available-count/24}
    if index==len(job['segments'])-1 and external.get('next'):
        spec['neighbors']['next'] = copy.deepcopy(external['next'])
    visible,generation = timing(segment['duration'],*[spec['neighbors'].get(s,{}).get('frames',0) for s in ('previous','next')])
    spec.update(visible_frames=visible,generation_length=generation,duration=visible/24)
    return spec


def compiler_setting(graph, value, seen=None):
    if not isinstance(value,list):return value
    seen = set() if seen is None else set(seen)
    key, slot = str(value[0]),value[1]
    if key in seen:raise ValueError('Cycle in reference compiler settings.')
    seen.add(key)
    node = graph[key]
    if node['class_type'] in ('PrimitiveInt','PrimitiveFloat','PrimitiveBoolean','PrimitiveString') and slot==0:
        return compiler_setting(graph,node['inputs']['value'],seen)
    if node['class_type']=='SKEBAH3PromptListValidator' and slot in (1,2):
        enabled = compiler_setting(graph,node['inputs'].get('validation_enabled',True),seen)
        return ('deterministic' if enabled else 'legacy') if slot==1 else enabled
    raise ValueError(f'Cannot preflight reference compiler setting from {node["class_type"]}. Use a literal setting or a primitive in the registered workflow.')


async def checked_graph(server, template, spec, compiler_check=False):
    # These imports are delayed to avoid Comfy's custom-node import cycle.
    import execution
    import nodes
    graph = redo_graph(template,spec)
    graph = server.trigger_on_prompt({'prompt':graph})['prompt']
    server.node_replace_manager.apply_replacements(graph)
    valid = await execution.validate_prompt(str(uuid.uuid4()),graph,None)
    if not valid[0]:
        raise ValueError(json.dumps({'error':valid[1],'node_errors':valid[3]},ensure_ascii=False))
    if compiler_check:
        for node in graph.values():
            if node['class_type']!='H3TaggedReferencePrompt':
                continue
            cls = nodes.NODE_CLASS_MAPPINGS[node['class_type']]
            values = node['inputs']
            allowed = inspect.signature(cls.build).parameters
            settings = {k:compiler_setting(graph,v) for k,v in values.items() if k in allowed and k!='prompt_template'}
            await asyncio.to_thread(cls().build, generation_prompt(spec), **{**settings,'defer_media_loading':True})
    return graph,valid[2]


async def start_batch(server, token, identifier, resume=False):
    key = (token,identifier)
    if key in _TASKS:
        raise ValueError('This batch is already running.')
    job = batch_job(token,identifier)
    if job['state']=='completed':
        return {'batch_id':identifier,'managed':True}
    # Do not resubmit any child still in the queue after refresh/reconnect.
    running,pending = server.prompt_queue.get_current_queue()
    active = {row[1] for row in running+pending}
    _,doc = reconcile_jobs(token,server.prompt_queue)
    if any(j.get('prompt_id') in active for j in doc['jobs'] if j['id'] in job['children']):
        raise ValueError('A batch clip is still queued or running. Wait for it to finish before resuming.')
    if not resume and job['state']!='prepared':
        raise ValueError('Use Resume from failed clip to continue this batch.')
    set_batch(token,identifier,state='running',error='',runner_session=_SESSION)
    task = asyncio.create_task(run_batch(server,token,identifier))
    _TASKS[key] = task
    task.add_done_callback(lambda completed:_TASKS.pop(key,None))
    return {'batch_id':identifier,'managed':True}


async def run_batch(server,token,identifier):
    try:
        job = batch_job(token,identifier)
        # Compile every prompt and validate both passes before enqueueing any generation.
        for index in range(len(job['segments'])):
            if batch_job(token,identifier)['state']=='canceled':return
            try:
                await checked_graph(server,job['template_snapshot'],child_spec(job,index),compiler_check=True)
            except Exception as error:
                raise ValueError(f'Prompt {index+1}: {error}') from error
        previous = None
        for index in range(len(job['segments'])):
            job = batch_job(token,identifier)
            if job['state']=='canceled':return
            _,doc = playlist_manifest(token)
            children = job['children']
            saved = next((j for j in doc['jobs'] if index<len(children) and j['id']==children[index]),None)
            if saved and saved['state']=='completed':
                previous = next(c for c in doc['clips'] if c['clip_id']==saved['clip_id'])
                playlist_media(token,previous['clip_id'])
                continue
            spec = child_spec(job,index,previous)
            graph,outputs = await checked_graph(server,job['template_snapshot'],spec)
            prompt_id = str(uuid.uuid4())
            with _MANIFEST_LOCK:
                directory,doc = playlist_manifest(token)
                parent = next(j for j in doc['jobs'] if j['id']==identifier)
                if parent['state']=='canceled':return
                children = parent['children']
                if index<len(children):children[index]=spec['request_id']
                else:children.append(spec['request_id'])
                parent['current'] = index+1
                doc['jobs'].append({'id':spec['request_id'],'prompt_id':prompt_id,'state':'queued',
                                    'spec':spec,'output_node':job['template_snapshot']['output']})
                write_project(directory,doc)
                number = server.number
                server.number += 1
                server.prompt_queue.put((number,prompt_id,graph,{},outputs,{}))
            while True:
                await asyncio.sleep(1)
                _,doc = reconcile_jobs(token,server.prompt_queue)
                if batch_job(token,identifier)['state']=='canceled':return
                saved = next(j for j in doc['jobs'] if j['id']==spec['request_id'])
                if saved['state']=='completed':
                    # Wait for execution to leave the queue before submitting the next clip.
                    running,pending = server.prompt_queue.get_current_queue()
                    if any(row[1]==prompt_id for row in running+pending):continue
                    previous = next(c for c in doc['clips'] if c['clip_id']==saved['clip_id'])
                    break
                if saved['state'] in ('failed','canceled'):
                    raise ValueError(f'Prompt {index+1}: {saved.get("error",saved["state"])}')
        await asyncio.to_thread(finish_batch,token,identifier)
    except asyncio.CancelledError:
        set_batch(token,identifier,state='failed',error='Batch interrupted. Resume to continue from the first unfinished clip.')
        raise
    except Exception as error:
        try:
            set_batch(token,identifier,state='failed',error=str(error))
        except FileNotFoundError:
            pass  # The canceled project may have been deleted while preflight was running.


def finish_batch(token,identifier):
    job = batch_job(token,identifier)
    if job['state']=='canceled':return
    directory,doc = playlist_manifest(token)
    jobs = {j['id']:j for j in doc['jobs']}
    paths = [playlist_media(token,jobs[c]['clip_id']) for c in job['children']]
    spec = job['spec']
    generated = directory/('batch_'+identifier+'.mp4')
    output = directory/('edited_batch_'+identifier+'.mp4')
    crf = job['template_snapshot']['graph'][job['template_snapshot']['output']]['inputs'].get('crf')
    crf = 18 if crf is None else crf
    try:
        count = assemble_generated(spec,paths,[s['duration'] for s in job['segments']],generated,crf)
        if _clip_metadata(generated)['frame_count']!=count:raise ValueError('Batch frame count mismatch.')
        expected = assemble_section(spec,generated,output,crf)
        metadata = _clip_metadata(output)
        if metadata['frame_count']!=expected:raise ValueError('Assembled batch frame count mismatch.')
        with _MANIFEST_LOCK:
            directory,doc = playlist_manifest(token)
            parent = next(j for j in doc['jobs'] if j['id']==identifier)
            if parent['state']=='canceled':return
            record = {**metadata,'clip_id':output.stem,'index':len(doc['clips'])+1,
                      'media_role':'new_clip' if spec['edit']['mode']=='insert_between' else 'alternate',
                      'seed':spec['seed'],'parent_clip_id':spec['parent_clip_id'],
                      'prompt':spec['prompt'],'redo':spec,'batch_clips':[jobs[c]['clip_id'] for c in job['children']]}
            doc['clips'].append(record)
            doc['revision'] += 1
            parent.update(state='completed',clip_id=output.stem)
            write_project(directory,doc)
    finally:
        generated.unlink(missing_ok=True)
        if batch_job(token,identifier)['state']!='completed':output.unlink(missing_ok=True)


def reconcile_batches(token,server):
    directory,doc = reconcile_jobs(token,server.prompt_queue)
    with _MANIFEST_LOCK:
        directory,doc = playlist_manifest(token)
        changed = False
        for job in doc['jobs']:
            if (job.get('kind')=='batch' and (job['state']=='running' or
                    (job['state']=='prepared' and job.get('runner_session')!=_SESSION)) and (token,job['id']) not in _TASKS):
                job.update(state='failed',error='Batch interrupted. Resume to continue from the first unfinished clip.')
                changed = True
        if changed:write_project(directory,doc)
    return directory,doc


def cancel_batch(server,token,identifier):
    job = set_batch(token,identifier,state='canceled',error='Canceled by user. Completed clips are kept.')
    _,doc = playlist_manifest(token)
    ids = {j.get('prompt_id') for j in doc['jobs'] if j['id'] in job['children']}
    server.prompt_queue.delete_queue_item(lambda row:row[1] in ids)
    running,_ = server.prompt_queue.get_current_queue()
    if any(row[1] in ids for row in running):comfy.model_management.interrupt_current_processing()
    return {'batch_id':identifier,'state':'canceled'}
