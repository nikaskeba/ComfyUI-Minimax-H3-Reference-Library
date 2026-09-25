import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage();
 await page.route('http://guide.test/',route=>route.fulfill({contentType:'text/html',body:'<main style="width:480px;height:400px"></main>'}));
 await page.goto('http://guide.test/');
 const code=await fs.readFile(new URL('../web/workflow_guide.js',import.meta.url),'utf8');
 await page.evaluate(code=>{
  const app={registerExtension(ext){window.ext=ext;}};
  new Function('app',code.replace(/^import .*;\r?\n/gm,'').replace(/export function/g,'function'))(app);
  class Guide {
   constructor(){this.widgets=[{name:'html',value:'<h2 style="color:rgb(255, 0, 0)">Test guide</h2><details><summary>More</summary>Instructions</details>'}];}
   addDOMWidget(name,type,element){document.querySelector('main').append(element);}
   setSize(){}
  }
  ext.beforeRegisterNodeDef(Guide,{name:'SkebaWorkflowGuide'});
  window.guide=new Guide();guide.onNodeCreated();
 },code);
 const frame=page.frameLocator('iframe');
 await frame.getByRole('heading',{name:'Test guide'}).waitFor();
 assert.equal(await frame.locator('h2').evaluate(e=>getComputedStyle(e).color),'rgb(255, 0, 0)');
 await frame.getByText('More',{exact:true}).click();assert.equal(await frame.locator('details').getAttribute('open'),'');
 await frame.locator('h2').dblclick();
 const editor=page.getByRole('textbox',{name:'Workflow guide HTML'});
 await editor.waitFor({state:'visible'});
 const html='<style>body{color:rgb(0,255,0)}</style><h1>New guide</h1><script>parent.guideInjected=true</script><img src="x" onerror="parent.guideInjected=true"><a href="javascript:alert(1)">Bad</a><a href="https://example.com">Link</a><iframe src="https://example.com"></iframe><meta http-equiv="refresh" content="0;url=https://example.com">';
 await editor.fill(html);
 assert.equal(await page.evaluate(()=>guide.widgets[0].value),html);
 await page.getByRole('button',{name:'Preview',exact:true}).click();
 await frame.getByRole('heading',{name:'New guide'}).waitFor();
 assert.equal(await frame.locator('script,iframe,meta[http-equiv=refresh],[onerror]').count(),0);
 assert.equal(await frame.getByText('Bad',{exact:true}).getAttribute('href'),null);
 assert.equal(await frame.getByText('Link',{exact:true}).getAttribute('rel'),'noopener noreferrer');
 assert.equal(await page.evaluate(()=>window.guideInjected),undefined);
 assert.equal(await page.locator('body').evaluate(e=>getComputedStyle(e).color),'rgb(0, 0, 0)');
 await page.getByRole('button',{name:'Edit HTML'}).click();assert.equal(await editor.inputValue(),html);
 await editor.fill('<h2>Saved guide</h2><p>Reloaded content</p>');
 await page.evaluate(()=>guide.onConfigure());
 await frame.getByRole('heading',{name:'Saved guide'}).waitFor();
 await frame.locator('h2').dblclick();await editor.press('Control+Enter');await frame.locator('h2').waitFor();
 await page.screenshot({path:process.env.TEMP+'/skeba-html-guide.png'});
 console.log('HTML guide rendering, double-click editing, persistence, CSS isolation and script blocking passed');
}finally{await browser.close();}
