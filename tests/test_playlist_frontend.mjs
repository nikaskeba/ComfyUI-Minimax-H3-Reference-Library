import assert from 'node:assert/strict';

import fs from 'node:fs/promises';

import {createRequire} from 'node:module';

const {chromium}=createRequire(import.meta.url)('playwright');

const browser=await chromium.launch({headless:true,channel:'chrome'});

try {

 const page=await browser.newPage({viewport:{width:1440,height:2200}}), errors=[];

 page.on('pageerror',e=>errors.push(e.message));

 let submitted, redoPayload, legacy=false;

 const doc={section_editing:true,clip_deletion:true,timeline_trimming:true,revision:0,undo:[],redo:[],jobs:[],directory:'Test episode',timeline:[{id:'ta',clip_id:'a'},{id:'tb',clip_id:'b'}],clips:[

  {clip_id:'a',index:1,filename:'a.mp4',duration_seconds:15,prompt:'First prompt'},

  {clip_id:'b',index:2,filename:'b.mp4',seed:0,duration_seconds:12,prompt:'Second prompt'},

  {clip_id:'c',index:3,filename:'alternate.mp4',duration_seconds:12,prompt:'Alternate',parent_clip_id:'b'}]};

 await page.route('http://playlist.test/**',async route=>{

  const url=new URL(route.request().url()),json=body=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)});

  if(url.pathname==='/h3-video-playlist')return route.fulfill({contentType:'text/html',body:await fs.readFile(new URL('../manager/playlist.html',import.meta.url),'utf8')});

  if(url.pathname.endsWith('/projects')&&route.request().method()==='POST'){assert.equal(route.request().postDataJSON().name,'Imported project');doc.clips=[];doc.timeline=[];doc.undo=[];doc.redo=[];return json({id:'project1',name:'Imported project'});}
  if(url.pathname.endsWith('/import')){assert.match(route.request().headers()['content-type'],/multipart/);doc.clips.push({clip_id:'imported',filename:'imported.mp4',source_filename:'outside.mp4',duration_seconds:3,prompt:''});doc.timeline.push({id:'ti',clip_id:'imported'});return json(doc.clips.at(-1));}
  if(url.pathname.endsWith('/projects'))return json([{id:'project1',name:'Test episode'}]);

  if(url.pathname.endsWith('/templates/template1')&&route.request().method()==='DELETE')return json({removed:'template1'});
  if(url.pathname.endsWith('/templates'))return json([{id:'template1',name:'Two-pass H3'}]);

  if(url.pathname.endsWith('/project1'))return json(legacy?{clips:doc.clips,directory:doc.directory,schema_version:1}:doc);

  if(url.pathname.endsWith('/timeline')){const p=route.request().postDataJSON();assert.equal(p.revision,doc.revision);if(p.action==='undo'){doc.redo.push(doc.timeline);doc.timeline=doc.undo.pop();}else if(p.action==='redo'){doc.undo.push(doc.timeline);doc.timeline=doc.redo.pop();}else if(p.action==='rename'){doc.name=p.name;}else if(p.action==='delete'){doc.clips=doc.clips.filter(c=>c.clip_id!==p.clip_id);doc.timeline=doc.timeline.filter(e=>e.clip_id!==p.clip_id);}else{doc.undo.push(doc.timeline);doc.redo=[];doc.timeline=p.timeline;}doc.revision++;return json(doc);}

  if(url.pathname.endsWith('/redo')){redoPayload=route.request().postDataJSON();return json({request_id:'redo1',prompt_id:'queue1',graph:{'test':{class_type:'SkebaPlaylistRedoSave',inputs:{}}}});}

  if(url.pathname.endsWith('/job'))return json({});

  if(url.pathname==='/prompt'){submitted=route.request().postDataJSON();return json({prompt_id:'queue1'});}

  if(url.pathname==='/history/queue1')return json({queue1:{status:{status_str:'success'},outputs:{'1':{text:['combined_test.mp4']}}}});

  return route.fulfill({status:204});

 });

 await page.goto('http://playlist.test/h3-video-playlist?client_id=comfy-test-client');await page.locator('#clips .timeline-clip').nth(1).waitFor();

 assert.equal(await page.locator('#clips').evaluate(el=>getComputedStyle(el).flexDirection),'row');

 // Use synthetic media events: fixture MP4 requests intentionally contain no media.

 await page.evaluate(()=>{const p=document.getElementById('player');p.play=async()=>{};p.onerror=null;});

 await page.locator('#clips .timeline-clip').first().click();await page.locator('#player').dispatchEvent('ended');

 assert.equal(await page.locator('#clips .timeline-clip.active').getAttribute('data-entry'),'tb');

 await page.locator('#media [data-clip="c"]').getByText('Preview',{exact:true}).click();

 assert.match(await page.locator('#asset-player').getAttribute('src'),/clip\/c$/);assert.match(await page.locator('#player').getAttribute('src'),/clip\/b$/);await page.locator('#close-preview').click();

 await page.locator('#clips .timeline-clip').first().click();await page.locator('#stop').click();

 await page.locator('#player').dispatchEvent('ended');assert.equal(await page.locator('#clips .timeline-clip.active').getAttribute('data-entry'),'ta');

 await page.locator('#player').dispatchEvent('play');await page.locator('#player').dispatchEvent('ended');

 assert.equal(await page.locator('#clips .timeline-clip.active').getAttribute('data-entry'),'tb');

 await page.locator('#media [data-clip="c"]').dragTo(page.locator('#clips .timeline-clip').first(),{sourcePosition:{x:40,y:25},targetPosition:{x:20,y:30}});

 await page.waitForFunction(()=>document.querySelectorAll('#clips .timeline-clip').length===3);assert.deepEqual(doc.timeline.map(e=>e.clip_id),['c','a','b']);

 await page.locator('#undo').click();await page.waitForFunction(()=>document.querySelectorAll('#clips .timeline-clip').length===2);

 await page.locator('#clips .timeline-clip').first().locator('.remove-clip').click();

 await page.waitForFunction(()=>document.querySelectorAll('#clips .timeline-clip').length===1);assert.equal(doc.clips.length,3);

 await page.locator('#undo').click();await page.waitForFunction(()=>document.querySelectorAll('#clips .timeline-clip').length===2);



 async function checkTimelinePosition(seconds,entry){

  const geometry=await page.evaluate(()=>{const bar=document.getElementById('scrub').getBoundingClientRect(),clips=[...document.querySelectorAll('#clips .timeline-clip')].map(b=>b.getBoundingClientRect());return {x:bar.x,y:bar.y+bar.height/2,width:bar.width,first:clips[0].x,last:clips.at(-1).right};});

  assert.ok(Math.abs(geometry.x-geometry.first)<1);

  assert.ok(Math.abs(geometry.x+geometry.width-geometry.last)<1);

  await page.mouse.click(geometry.x+geometry.width*seconds/27,geometry.y);

  assert.ok(Math.abs(Number(await page.locator('#scrub').inputValue())-seconds)<.06);

  assert.equal(await page.locator('#clips .timeline-clip.active').getAttribute('data-entry'),entry);

 }

 await checkTimelinePosition(8,'ta');await checkTimelinePosition(20,'tb');

 await page.locator('#zoom').fill('60');await page.locator('#zoom').dispatchEvent('input');

 await page.locator('#timeline-scroll').evaluate(el=>{el.scrollLeft=200;});

 await checkTimelinePosition(20,'tb');await checkTimelinePosition(26,'tb');

 await page.locator('#zoom').fill('16');await page.locator('#zoom').dispatchEvent('input');



 await page.locator('#clips .timeline-clip').nth(1).click();await page.locator('#clips .timeline-clip').nth(1).locator('.remove-clip').click();

 await page.waitForFunction(()=>document.querySelectorAll('#clips .timeline-clip').length===1);

 assert.equal(doc.clips.length,3);await page.locator('#undo').click();await page.waitForFunction(()=>document.querySelectorAll('#clips .timeline-clip').length===2);

 await page.locator('#clips .timeline-clip').nth(1).click();

 await page.locator('#media .asset').filter({hasText:'alternate.mp4'}).getByText('Insert after',{exact:true}).click();

 await page.waitForFunction(()=>document.querySelectorAll('#clips .timeline-clip').length===3);

 assert.deepEqual(doc.timeline.map(e=>e.clip_id),['a','b','c']);

 // Drag the first clip to the far side of the third clip.

 await page.locator('#clips .timeline-clip').nth(0).dragTo(page.locator('#clips .timeline-clip').nth(2),{targetPosition:{x:175,y:30}});

 await page.waitForTimeout(100);assert.notEqual(doc.timeline[0].clip_id,'a');

 await page.locator('#undo').click();await page.waitForTimeout(100);assert.equal(doc.timeline[0].clip_id,'a');

 await page.locator('#clips .timeline-clip').nth(1).click();await page.locator('#regenerate').click();

 await page.locator('#template option').waitFor({state:'attached'});assert.equal(await page.locator('#redo-prompt').inputValue(),'Second prompt');assert.equal(await page.locator('#seed').inputValue(),'0');

 assert.equal(await page.locator('#previous-enabled').isChecked(),false);assert.equal(await page.locator('#next-enabled').isChecked(),false);

 await page.locator('#redo-prompt').fill('Edited second prompt');await page.locator('#duration').fill('5');await page.locator('#previous-enabled').check();await page.locator('#previous-frames').selectOption('39');await page.locator('#previous-audio').uncheck();await page.locator('#submit-redo').click();

 await page.locator('#redo-dialog').waitFor({state:'hidden'});assert.equal(redoPayload.prompt,'Edited second prompt');assert.equal(redoPayload.duration,5);assert.deepEqual(redoPayload.previous,{enabled:true,frames:39,audio:false});assert.equal(redoPayload.next.enabled,false);assert.equal(submitted.prompt_id,'queue1');assert.equal(submitted.client_id,'comfy-test-client');

 // Both handles remain available in insertion mode, including a zero-width cut.

 await page.locator('#regenerate').click();await page.locator('#edit-mode').selectOption('insert');

 assert.equal(await page.locator('#cut-in').isVisible(),true);assert.equal(await page.locator('#cut-out').isVisible(),true);

 assert.equal(await page.locator('#redo-prompt').inputValue(),'Second prompt');

 await page.locator('#cut-start').fill('4');await page.locator('#cut-start').dispatchEvent('change');

 await page.locator('#cut-end').fill('9');await page.locator('#cut-end').dispatchEvent('change');

 assert.equal(Number(await page.locator('#cut-end').inputValue())-Number(await page.locator('#cut-start').inputValue()),5);

 const handle=await page.locator('#cut-out').boundingBox(),track=await page.locator('#cut-track').boundingBox();

 await page.mouse.move(handle.x+handle.width/2,handle.y+handle.height/2);await page.mouse.down();await page.mouse.move(track.x+track.width*10/12,handle.y+handle.height/2);await page.mouse.up();

 assert.ok(Math.abs(Number(await page.locator('#cut-end').inputValue())-10)<.1);

 await page.locator('#keep-original').click();assert.equal(await page.locator('#cut-end').inputValue(),await page.locator('#cut-start').inputValue());

 await page.locator('#cut-end').fill('9');await page.locator('#cut-end').dispatchEvent('change');

 await page.locator('#redo-prompt').fill('Replacement action starting at zero.');await page.locator('#submit-redo').click();

 await page.locator('#redo-dialog').waitFor({state:'hidden'});

 assert.deepEqual(redoPayload.edit,{mode:'insert',start:4,end:9,side:'after'});assert.equal(redoPayload.duration,5);

 assert.equal(redoPayload.previous.enabled,true);assert.equal(redoPayload.next.enabled,true);

 // Play resumes without assigning src (which would reset playback).
 await page.locator('#clips .timeline-clip').nth(1).click();await page.locator('#stop').click();
 const resume=await page.evaluate(async()=>{const p=document.getElementById('player');p.currentTime=2;let changed=0;const observer=new MutationObserver(records=>changed+=records.filter(r=>r.attributeName==='src').length);observer.observe(p,{attributes:true});document.getElementById('sequence').click();await Promise.resolve();observer.disconnect();return {time:p.currentTime,changed};});
 assert.equal(resume.time,2);assert.equal(resume.changed,0);await page.locator('#stop').click();
 // A bridge captures the two neighboring clips and generates a standalone insert.
 await page.locator('#clips .timeline-clip').first().click();await page.locator('#clip-right').click();
 assert.equal(await page.locator('#edit-mode').inputValue(),'insert_between');
 assert.equal(await page.locator('#boundary-side').inputValue(),'after');
 assert.equal(await page.locator('#previous-enabled').isChecked(),true);assert.equal(await page.locator('#next-enabled').isChecked(),true);
 assert.match(await page.locator('#previous-name').textContent(),/a.mp4/);assert.match(await page.locator('#next-name').textContent(),/b.mp4/);
 await page.locator('#redo-prompt').fill('Bridge the two scenes.');await page.locator('#submit-redo').click();await page.locator('#redo-dialog').waitFor({state:'hidden'});
 assert.equal(redoPayload.edit.mode,'insert_between');assert.equal(redoPayload.entry_id,'ta');assert.equal(redoPayload.duration,5);
 await page.locator('#clips .timeline-clip').first().getByText('Info',{exact:true}).click();assert.equal(await page.locator('#info-prompt').textContent(),'First prompt');await page.locator('#close-info').click();
 await page.locator('#media-filter').selectOption('edits');assert.equal(await page.locator('#media [data-clip="a"]').isVisible(),false);assert.equal(await page.locator('#media [data-clip="c"]').isVisible(),true);await page.locator('#media-filter').selectOption('all');
 // Trim handles shorten an occurrence while the project clip stays full length.
 const trim=page.locator('#clips .timeline-clip').nth(1).locator('.trim-start');const box=await trim.boundingBox();
 const px=await page.locator('#timeline-track').evaluate(el=>el.getBoundingClientRect().width/39);
 await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+px*2,box.y+box.height/2);assert.equal(await page.locator('#trim-preview').isVisible(),true);assert.match(await page.locator('#trim-time').textContent(),/retained frame/);await page.mouse.up();assert.equal(await page.locator('#trim-preview').isVisible(),false);
 await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('timeline clips'));
 assert.ok(Math.abs(doc.timeline[1].in_frame-48)<=1);assert.equal(doc.clips[1].duration_seconds,12);
 await page.locator('#undo').click();await page.waitForTimeout(100);assert.equal(doc.timeline[1].in_frame,undefined);
 // An emptied timeline still accepts saved clips and all edits can be undone.

 for(let count=3;count>0;count--){await page.locator('#clips .timeline-clip').first().locator('.remove-clip').click();await page.waitForFunction(n=>document.querySelectorAll('#clips .timeline-clip').length===n,count-1);}

 await page.locator('#media [data-clip="c"]').dragTo(page.locator('#clips'),{sourcePosition:{x:40,y:25}});

 await page.waitForFunction(()=>document.querySelectorAll('#clips .timeline-clip').length===1);assert.deepEqual(doc.timeline.map(e=>e.clip_id),['c']);

 for(const count of [0,1,2,3]){await page.locator('#undo').click();await page.waitForFunction(n=>document.querySelectorAll('#clips .timeline-clip').length===n,count);}

 await page.locator('#create').click();await page.locator('#final').waitFor({state:'visible'});assert.equal(submitted.client_id,'comfy-test-client');assert.deepEqual(JSON.parse(submitted.prompt['1'].inputs.clip_ids),['a','b','c']);

 await page.reload();await page.locator('#clips .timeline-clip').nth(2).waitFor();

 await page.screenshot({path:process.env.TEMP+'/h3-playlist-editor.png',fullPage:true});

 page.once('dialog',d=>d.accept('Renamed episode'));await page.locator('#rename-project').click();await page.waitForFunction(()=>document.querySelector('#projects'));await page.waitForTimeout(100);assert.equal(doc.name,'Renamed episode');
 assert.equal(await page.locator('#bridge-clip').count(),0);assert.equal(await page.locator('#clip-list').count(),0);

 page.once('dialog',d=>d.accept());await page.locator('#media [data-clip="c"]').locator('.delete-clip').click();await page.waitForFunction(()=>!document.querySelector('#media [data-clip="c"]'));assert.equal(doc.clips.length,2);

 page.once('dialog',d=>d.accept('Imported project'));await page.locator('#new-project').click();await page.waitForFunction(()=>document.querySelectorAll('#clips .timeline-clip').length===0);
 await page.locator('#import-files').setInputFiles({name:'outside.mp4',mimeType:'video/mp4',buffer:Buffer.from('mock video upload')});await page.locator('#clips .timeline-clip').waitFor();await page.locator('#clips .timeline-clip').click();await page.locator('#regenerate').click();assert.equal(await page.locator('#redo-prompt').inputValue(),'');page.once('dialog',d=>d.accept());await page.locator('#remove-template').click();await page.waitForFunction(()=>document.querySelector('#template').options.length===0);await page.locator('#close-redo').click();
 legacy=true;await page.reload();await page.locator('#clips .timeline-clip').first().waitFor();assert.equal(await page.locator('#regenerate').isDisabled(),true);assert.match(await page.locator('#status').textContent(),/Restart ComfyUI/);

 assert.deepEqual(errors,[]);console.log('Playlist timeline editing, alternate insertion, redo submission, persistence and compilation passed');

} finally {await browser.close();}

