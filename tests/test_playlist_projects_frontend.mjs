import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 let projects=Array.from({length:10},(_,i)=>({id:'p'+i,name:'Episode '+i,updated_at:1700000000+i,clip_count:3,duration_seconds:65})),deleted;
 await page.route('http://playlist.test/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  const json=data=>route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  if(path==='/h3-video-playlist')return route.fulfill({contentType:'text/html',body:await fs.readFile(new URL('../manager/playlist.html',import.meta.url),'utf8')});
  if(route.request().method()==='DELETE'){deleted=path.split('/').at(-1);projects=projects.filter(p=>p.id!==deleted);return json({deleted});}
  if(path.endsWith('/projects'))return json(projects);
  return json({clips:[],timeline:[],jobs:[],undo:[],redo:[],revision:0});
 });
 await page.goto('http://playlist.test/h3-video-playlist');await page.locator('#choose-project').click();
 await page.waitForFunction(()=>document.querySelectorAll('.project-row').length===8);
 assert.match(await page.locator('.project-row').first().textContent(),/3 saved clips · 1:05/);
 await page.locator('#project-next').click();assert.equal(await page.locator('.project-row').count(),2);
 await page.locator('#project-search').fill('Episode 9');assert.equal(await page.locator('.project-row').count(),1);
 page.once('dialog',d=>d.dismiss());await page.locator('.project-delete').click();assert.equal(deleted,undefined);
 page.once('dialog',d=>d.accept());await page.locator('.project-delete').click();await page.waitForFunction(()=>document.querySelector('#project-list').textContent==='No projects found.');assert.equal(deleted,'p9');
 await page.locator('#project-search').fill('Episode 0');await page.locator('.project-row button').first().click();assert.equal(await page.locator('#project-dialog').isVisible(),false);
 assert.deepEqual(errors,[]);console.log('Project chooser pagination, search, opening and confirmed deletion passed');
} finally {await browser.close();}
