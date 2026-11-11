import {test,expect,chromium} from '@playwright/test';
import serverChromium from '@sparticuz/chromium';

test('chat copy controls: whole response, requested placement, exact blocks and browser fallbacks',async()=>{
 test.skip(process.env.HAYTILE_OFFLINE_CREATIONS!=='1','Offline provider only.');
 const browser=await chromium.launch({executablePath:await serverChromium.executablePath(),args:serverChromium.args.filter(x=>x!=='--disable-web-security'),headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const base=process.env.HAYTILE_TEST_URL||'http://127.0.0.1:8010';
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{
  if(window.top!==window)return;
  localStorage.setItem('haytile-locale','en');
  Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async(value:string)=>{(window as any).fixtureClipboard=value;}}});
 });
 const login=await page.request.post(base+'/api/v1/auth/login',{data:{email:'creative-browser@example.test',password:'Offline-browser-password-123'},headers:{Origin:base}});expect(login.status()).toBe(200);
 await page.goto(base);await expect(page.locator('.user-line strong')).toHaveText('Creative browser fixture');
 await page.getByRole('button',{name:'New chat',exact:true}).click();
 const before=(await (await page.request.get(base+'/api/v1/wallet')).json()).balance;
 let jobCalls=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/jobs'))jobCalls++;});
 await page.getByRole('textbox',{name:'Your message',exact:true}).fill('Offline copy controls');
 await page.getByRole('button',{name:'Send message',exact:true}).click();
 const blocks=page.locator('.chat-copy-block');await expect(blocks).toHaveCount(3,{timeout:20000});
 const prompt='Prompt: Yon jèn fi ak yon gason, anba limyè lalin.\nPa chanje pawòl yo.';
 const style='Konpa modèn, pyano, duo gason ak fi, 96 BPM.';
 const code="const title = '<script>not executable</script>';\nconsole.log(title);";
 await expect(blocks.nth(0).locator(':scope > :first-child')).toHaveClass('chat-copy-block-bar');
 await expect(blocks.nth(1).locator(':scope > :last-child')).toHaveClass('chat-copy-block-bar');
 await blocks.nth(0).getByRole('button',{name:'Copy block',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>(window as any).fixtureClipboard)).toBe(prompt);
 await expect(blocks.nth(0)).toContainText('Copied.');
 await blocks.nth(1).getByRole('button',{name:'Copy block',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>(window as any).fixtureClipboard)).toBe(style);
 await blocks.nth(2).getByRole('button',{name:'Copy block',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>(window as any).fixtureClipboard)).toBe(code);
 await page.locator('.chat-answer-actions').getByRole('button',{name:'Copy text',exact:true}).click();
 const whole=await page.evaluate(()=>(window as any).fixtureClipboard);
 expect(whole).toContain(prompt);expect(whole).toContain(style);expect(whole).toContain('A final explanation');
 expect(whole).toContain('```copy-after');
 // Clipboard permission denied: the local legacy path still copies the exact block.
 await page.evaluate(()=>{
  Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw new Error('NotAllowedError');}}});
  document.execCommand=((command:string)=>{if(command==='copy'){(window as any).fixtureClipboard=(document.activeElement as HTMLTextAreaElement).value;return true;}return false;}) as typeof document.execCommand;
 });
 await blocks.nth(1).getByRole('button',{name:'Copy block',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>(window as any).fixtureClipboard)).toBe(style);
 // Neither API available: honest manual selection, never a false "Copied" success.
 await page.evaluate(()=>{document.execCommand=()=>false;});
 await page.setViewportSize({width:390,height:844});
 expect(await blocks.nth(1).locator('pre').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
 await blocks.nth(2).getByRole('button',{name:'Copy block',exact:true}).click();
 const manual=page.getByRole('dialog',{name:'Copy this text',exact:true});await expect(manual).toBeVisible();
 const selected=manual.getByRole('textbox',{name:'Text to copy',exact:true});await expect(selected).toHaveValue(code);
 expect(await selected.evaluate((el:HTMLTextAreaElement)=>[el.selectionStart,el.selectionEnd])).toEqual([0,code.length]);
 await manual.getByRole('button',{name:'Close',exact:true}).click();await expect(manual).not.toBeVisible();
 await blocks.nth(1).scrollIntoViewIfNeeded();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'test-results/chat-copy-mobile.png',fullPage:true});
 expect(jobCalls).toBe(1);expect((await (await page.request.get(base+'/api/v1/wallet')).json()).balance).toBe(before);
 expect(errors).toEqual([]);await browser.close();
});
