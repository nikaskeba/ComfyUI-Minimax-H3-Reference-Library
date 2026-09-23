import { app } from '../../scripts/app.js';
import { api } from '../../scripts/api.js';
app.registerExtension({
    name: 'Skeba.PlaylistRedo',
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!['SkebaPlaylistRedoSave','SkebaPlaylistWorkflow'].includes(nodeData.name)) return;
        const serialized = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function (data) {
            const result = serialized?.apply(this, arguments);
            data.properties ||= {};
            data.properties.skeba_redo_crf = this.widgets?.find(w => w.name === 'crf')?.value ?? 18;
            return result;
        };
        const configured = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (data) {
            const result = configured?.apply(this, arguments);
            const widget = this.widgets?.find(w => w.name === 'crf');
            if (widget) {
                // CRF is this node's only numeric widget. Older files may put
                // the non-serializing registration button before or after it.
                widget.value = data.properties?.skeba_redo_crf
                    ?? data.widgets_values_named?.crf
                    ?? data.widgets_values?.find(value => typeof value === 'number' && Number.isFinite(value))
                    ?? 18;
            }
            return result;
        };
    },
    async nodeCreated(node) {
        if (!['SkebaPlaylistRedoSave','SkebaPlaylistWorkflow'].includes(node.comfyClass)) return;
        const shared = node.comfyClass === 'SkebaPlaylistWorkflow';
        node.properties ||= {};
        node.addWidget('button', shared ? 'Register / Update playlist workflow' : 'Register redo workflow', null, async () => {
            const name = window.prompt('Name this playlist workflow', node.properties.skeba_playlist_name || (shared ? 'Main H3 workflow' : 'H3 two-pass redo'));
            if (name === null) return;
            try {
                const { output } = await app.graphToPrompt();
                const response = await api.fetchApi('/api/h3-video-playlist/templates', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({name, graph:output, ...(shared ? {registration_id:String(node.id), template_id:node.properties.skeba_playlist_template || undefined} : {})}),
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.error || 'Could not register workflow.');
                if (shared) {
                    node.properties.skeba_playlist_template = data.id;
                    node.properties.skeba_playlist_name = name;
                    app.graph.setDirtyCanvas(true, true);
                }
                window.alert(`Saved ${data.name}. Select it in H3 Live Playlist when redoing a clip.`);
            } catch (error) { window.alert(error.message); }
        }, {serialize:false});
    },
});
