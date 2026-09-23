"""Extract the shared two-pass renderer from a batch workflow."""
import copy


class PlaylistWorkflow:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"images":("IMAGE",), "audio":("AUDIO",),
                            "upscale_connector":("SKEBA_H3_AV_CONNECTOR_BUNDLE",),
                            "crf":("INT",{"default":18,"min":0,"max":51})}}
    RETURN_TYPES = ()
    FUNCTION = "register"
    CATEGORY = "Skeba AI Nodes - Utilities/Playlist"
    # Registration is a frontend action, never an execution output.
    def register(self, images, audio, upscale_connector, crf=18):
        return ()


def extract_renderer(graph, registration_id):
    graph = copy.deepcopy(graph)
    registration = graph.get(str(registration_id))
    if not registration or registration.get('class_type') != 'SkebaPlaylistWorkflow':
        raise ValueError('The registration node is missing from the executable graph. Reload the workflow and retry.')
    ports = registration['inputs']
    bundle = ports.get('upscale_connector')
    if not isinstance(bundle,list) or len(bundle)!=2 or bundle[1]!=1 or graph.get(str(bundle[0]),{}).get('class_type')!='SkebaMiniMaxH3AVConnectorGuideTest':
        raise ValueError('Connect the upscale AV Connector bundle to the registration node.')
    for name in ('images','audio'):
        if not isinstance(ports.get(name),list):
            raise ValueError('Connect decoded images and audio before continuation trimming.')
    marker, finalizer, save = ('playlist_'+str(registration_id)+'_'+suffix for suffix in ('input','finalize','save'))
    if any(key in graph for key in (marker,finalizer,save)):
        raise ValueError('Playlist-generated node IDs conflict with this graph.')
    graph[marker]={'class_type':'SkebaPlaylistRedoInput','inputs':{'request':'{}'}}
    graph[finalizer]={'class_type':'SkebaH3AVConnectorFinalizeTest','inputs':{
        'generated_images':ports['images'],'generated_audio':ports['audio'],'connector_bundle':bundle}}
    graph[save]={'class_type':'SkebaPlaylistRedoSave','inputs':{
        'images':[finalizer,0],'audio':[finalizer,1],'request':[marker,0],'crf':ports.get('crf',18)}}
    for node in graph.values():
        kind=node['class_type']; inputs=node.get('inputs',{})
        if kind=='SkebaCachedMiniMaxH3ReferenceFirstLast':
            inputs['length']=[marker,2]
            inputs.pop('first_frame',None);inputs.pop('last_frame',None)
        elif kind=='H3TaggedReferencePrompt':
            inputs['prompt_template']=[marker,1]
        elif kind=='SKEBAH3PromptListValidator':
            inputs['text']=[marker,1]
        elif kind=='RandomNoise':
            inputs['noise_seed']=[marker,3]
        elif kind=='SkebaMiniMaxH3AVConnectorGuideTest':
            inputs['bypass']=True
            for port in ('start_frames','end_frames','start_audio','end_audio'):
                inputs.pop(port,None)
    graph[str(bundle[0])]['inputs']['preserve_upscaled_endpoints']=True

    setters={}
    for key,node in graph.items():
        if node['class_type']=='Setter':
            inputs=node['inputs'];name=inputs.get('key') or inputs.get('var_name')
            if isinstance(name,str) and name:
                setters.setdefault(name,[]).append(inputs.get('value',inputs.get('obj')))

    def unwrap(value):
        seen=set()
        while isinstance(value,list) and len(value)==2 and isinstance(value[1],int):
            key=str(value[0]);node=graph.get(key)
            if not node:raise ValueError('Unresolved executable connection: '+key)
            kind=node['class_type'];inputs=node['inputs']
            if kind not in ('Getter','Setter','SKEBAMiniMaxH3MotionContext'):break
            if value[1]!=0:break
            if key in seen:raise ValueError('Cycle in shared workflow connections at '+key)
            seen.add(key)
            if kind=='Getter':
                if 'inp' in inputs:value=inputs['inp']
                else:
                    name=inputs.get('key') or inputs.get('var_name')
                    matches=setters.get(name,[]) if isinstance(name,str) else []
                    if len(matches)!=1:raise ValueError('Getter '+key+' needs one unambiguous Setter for '+str(name))
                    value=matches[0]
            elif kind=='Setter':value=inputs.get('value',inputs.get('obj'))
            else:value=inputs['conditioning']
        return value
    reachable=set()
    def visit(key):
        if key in reachable:return
        if key not in graph:raise ValueError('Unresolved executable node: '+key)
        reachable.add(key)
        graph[key]['inputs']={name:unwrap(value) for name,value in graph[key].get('inputs',{}).items()}
        for value in graph[key]['inputs'].values():
            if isinstance(value,list) and len(value)==2 and isinstance(value[1],int):visit(str(value[0]))
    visit(save)
    result={key:graph[key] for key in reachable}
    forbidden=('ForLoop','MotionContext','ContinuationTiming','SeamExposure','Accumulate','Getter','Setter','SkebaSaveClipToFile','SkebaCombine','SkebaFinish','SkebaCompile','SkebaPromptLoop','SkebaPromptFromList')
    bad=[key+': '+n['class_type'] for key,n in result.items() if any(t in n['class_type'] for t in forbidden)]
    if bad:raise ValueError('Unresolved batch dependencies in playlist renderer: '+', '.join(bad))
    normalize_reference_fps(result)
    return result


def normalize_reference_fps(graph):
    """Getter removal exposes INT -> FLOAT links rejected by Comfy validation."""
    for node in graph.values():
        if node.get('class_type') != 'H3TaggedReferencePrompt':
            continue
        inputs=node.get('inputs',{})
        link=inputs.get('video_fps')
        if not isinstance(link,list) or len(link)!=2 or link[1]!=0:
            continue
        source=graph.get(str(link[0]),{})
        if source.get('class_type')=='PrimitiveInt':
            value=source.get('inputs',{}).get('value')
            if type(value) in (int,float):
                inputs['video_fps']=float(value)
