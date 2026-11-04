import { test, expect, chromium } from '@playwright/test';
import serverChromium from '@sparticuz/chromium';
const base=process.env.HAYTILE_TEST_URL||'http://127.0.0.1:8010';
async function open() {
 const browser=await chromium.launch({executablePath:await serverChromium.executablePath(),args:[...serverChromium.args.filter(x=>x!=='--disable-web-security'),'--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'],headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 await page.addInitScript(()=>localStorage.setItem('haytile-locale','en'));
 await page.request.post(base+'/api/v1/auth/login',{data:{email:'creative-browser@example.test',password:'Offline-browser-password-123'},headers:{Origin:base}});
 return {browser,page};
}
test('native live PCM speech, interruption, mute and billing without text or TTS jobs',async()=>{
 test.skip(process.env.HAYTILE_OFFLINE_CREATIONS!=='1','Requires the explicit offline native provider.');
 const {browser,page}=await open();const jobs:any[]=[];const errors:string[]=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/api/v1/jobs'))jobs.push(r.postDataJSON());});
 await page.addInitScript(()=>{
  const stats=(window as any).__pcm={starts:0,stops:0};
  const start=AudioBufferSourceNode.prototype.start,stop=AudioBufferSourceNode.prototype.stop;
  AudioBufferSourceNode.prototype.start=function(...args:any[]){stats.starts++;return start.apply(this,args as any);};
  AudioBufferSourceNode.prototype.stop=function(...args:any[]){stats.stops++;return stop.apply(this,args as any);};
 });
 const before=await (await page.request.get(base+'/api/v1/wallet')).json();
 await page.goto(base);await page.getByRole('button',{name:'HAYTILE Chat',exact:true}).click();
 await page.getByRole('button',{name:'New chat',exact:true}).click();
 await page.locator('.chat-voice-preferences summary').click();
 await page.getByRole('combobox',{name:'Reply voice',exact:true}).selectOption('Charon');
 await expect(page.getByRole('combobox',{name:'Live voice model',exact:true})).toHaveValue('gemini-2.5-flash-native-audio-preview-12-2025');
 await page.locator('.chat-voice-preferences summary').click();
 await page.locator('.chat-input-box').getByRole('button',{name:'Start voice conversation',exact:true}).click();
 const call=page.getByRole('dialog',{name:'Voice conversation',exact:true});await expect(call).toBeVisible();
 await expect.poll(()=>page.evaluate(()=>(window as any).__pcm.starts),{timeout:30000}).toBeGreaterThanOrEqual(2);
 await expect.poll(()=>page.evaluate(()=>(window as any).__pcm.stops)).toBeGreaterThanOrEqual(1);
 await call.getByRole('button',{name:'Mute microphone',exact:true}).click();
 await expect(call.getByRole('button',{name:'Unmute microphone',exact:true})).toHaveAttribute('aria-pressed','true');
 await page.screenshot({path:'test-results/native-live-voice.png',fullPage:true});
 await call.getByRole('button',{name:'End voice conversation',exact:true}).click();await expect(call).not.toBeVisible();
 await expect.poll(async()=> (await(await page.request.get(base+'/api/v1/wallet')).json()).balance).toBe(before.balance-70);
 await expect(page.locator('.chat-user-bubble')).toHaveCount(0);await expect(page.locator('.chat-answer')).toHaveCount(0);
 expect(jobs).toEqual([]);await expect(page.locator('.chat-voice-audio')).toHaveCount(0);
 const observed=await(await page.request.get(base+'/api/v1/offline/live-observed')).json();expect(observed.frames).toBeGreaterThan(5);
 expect(observed.setups.at(-1).generationConfig.speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName).toBe('Charon');
 expect(errors).toEqual([]);await browser.close();
});
test('long chat scroll leaves header, sidebar and composer fixed on desktop and mobile',async()=>{
 test.skip(process.env.HAYTILE_OFFLINE_CREATIONS!=='1','Requires offline account.');
 const {browser,page}=await open();
 const cid='long-conversation-layout';
 await page.route('**/api/v1/chat/conversations',r=>r.fulfill({json:[{id:cid,title:'Long history'},...Array.from({length:80},(_,i)=>({id:'history-item-'+i,title:'History item '+i}))]}));
 await page.route('**/api/v1/chat/conversations/'+cid,r=>r.fulfill({json:Array.from({length:80},(_,i)=>({id:'long-turn-'+i,title:'Long history',prompt:'Question '+i,reply:('A long reply to verify scrolling. ').repeat(20),status:'completed'}))}));
 await page.goto(base);await page.getByRole('button',{name:'Long history',exact:true}).click();
 const transcript=page.locator('.chat-transcript'),composer=page.locator('.chat-input-box'),header=page.locator('.topbar'),sidebar=page.locator('.sidebar');
 await expect(page.locator('.chat-user-bubble')).toHaveCount(80);
 for(const size of [{width:1440,height:1000},{width:390,height:844}]){
  await page.setViewportSize(size);const before=await composer.boundingBox(),head=await header.boundingBox();
  await transcript.evaluate(e=>{e.scrollTop=e.scrollHeight;});await expect.poll(()=>transcript.evaluate(e=>e.scrollTop)).toBeGreaterThan(100);
  const after=await composer.boundingBox();expect(Math.abs(after!.y-before!.y)).toBeLessThan(1);expect(after!.y+after!.height).toBeLessThanOrEqual(size.height);
  expect((await header.boundingBox())!.y).toBe(head!.y);expect(await page.evaluate(()=>window.scrollY)).toBe(0);
  await transcript.evaluate(e=>{e.scrollTop=0;});expect((await composer.boundingBox())!.y).toBe(after!.y);
  if(size.width>700){expect((await sidebar.boundingBox())!.y).toBe(0);const brand=await page.locator('.brand').boundingBox(),profile=await page.locator('.user-line').boundingBox();await page.locator('.sidebar-chat-pane').evaluate(e=>{e.scrollTop=e.scrollHeight;});expect((await page.locator('.brand').boundingBox())!.y).toBe(brand!.y);expect((await page.locator('.user-line').boundingBox())!.y).toBe(profile!.y);}
  await page.screenshot({path:'test-results/fixed-chat-'+size.width+'.png'});
 }
 await browser.close();
});
