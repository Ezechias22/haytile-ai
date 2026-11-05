import {test, expect, chromium} from '@playwright/test';
import serverChromium from '@sparticuz/chromium';

test('offline chat files and assistant-requested location consent, no search toggle', async () => {
  test.skip(process.env.HAYTILE_OFFLINE_CREATIONS !== '1', 'Offline provider only.');
  const browser=await chromium.launch({executablePath:await serverChromium.executablePath(),args:serverChromium.args.filter(x=>x!=='--disable-web-security'),headless:true});
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const base=process.env.HAYTILE_TEST_URL || 'http://127.0.0.1:8010';
  const failures:string[]=[];
  page.on('pageerror',e=>failures.push(e.message));
  await page.addInitScript(()=>{
    if(window.top!==window) return;
    localStorage.setItem('haytile-locale','en');
    (window as any).fixtureGeoCalls=0;
    Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition(success:any,error:any){
      (window as any).fixtureGeoCalls++;
      if((window as any).fixtureGeoCalls===1)error({code:1});
      else success({coords:{latitude:18.543291,longitude:-72.343917}});
    }}});
  });
  const login=await page.request.post(base+'/api/v1/auth/login',{data:{email:'creative-browser@example.test',password:'Offline-browser-password-123'},headers:{Origin:base}});
  expect(login.status()).toBe(200);
  await page.goto(base);
  // Mobile menu should leave space for the composer and close after new chat.
  const sidebar=page.locator('.sidebar');
  if(!await page.getByRole('button',{name:'New chat',exact:true}).isVisible()) await page.getByRole('button',{name:/Open sidebar|Toggle sidebar|Open menu/}).first().click();
  await page.getByRole('button',{name:'New chat',exact:true}).click();
  if(await sidebar.isVisible()) {
    const close=page.getByRole('button',{name:/Close sidebar|Close menu/});
    if(await close.count()) await close.first().click();
  }
  expect(await page.evaluate(()=>(window as any).fixtureGeoCalls)).toBe(0);
  await expect(page.getByRole('button',{name:'Web search',exact:true})).toHaveCount(0);
  const composer=page.getByRole('textbox',{name:'Your message',exact:true});
  const sent:any[]=[];
  page.on('request',r=>{if(r.url().endsWith('/api/v1/jobs')&&r.method()==='POST') sent.push(r.postDataJSON());});
  await page.locator('.haytile-chat input[type=file]').setInputFiles({name:'private-reference.txt',mimeType:'text/plain',buffer:Buffer.from('Private document for offline reading.')});
  await expect(page.locator('.chat-tool-context')).toContainText('private-reference.txt');
  await composer.fill('Read this reference');
  await page.getByRole('button',{name:'Send message',exact:true}).click();
  await expect(page.getByRole('log')).toContainText('Offline reply:',{timeout:20000});
  expect(sent[0].params.attachment_ids).toHaveLength(1);
  expect(sent[0].params.location).toBeUndefined();
  await composer.fill('Find nearby offline hospital');
  await page.getByRole('button',{name:'Send message',exact:true}).click();
  const authorize=page.getByRole('button',{name:'Authorize location',exact:true});
  await expect(authorize).toBeVisible({timeout:20000});
  expect(await page.evaluate(()=>(window as any).fixtureGeoCalls)).toBe(0);
  await authorize.click();
  await expect(page.locator('.chat-tool-context')).toContainText('permission denied');
  expect(sent).toHaveLength(2);
  await authorize.click();
  await expect(page.getByRole('log')).toContainText('Nearby help found',{timeout:20000});
  expect(sent[2].params.location).toEqual({latitude:18.543,longitude:-72.344});
  await expect(page.getByRole('link',{name:'[1] Offline hospital source',exact:true})).toHaveAttribute('href','https://example.org/hospital');
  await expect(page.getByTitle('Google Search suggestions')).toHaveAttribute('sandbox','allow-popups allow-popups-to-escape-sandbox');
  expect(await page.evaluate(()=>(window as any).fixtureUnsafe)).toBeUndefined();
  const box=await composer.boundingBox();
  expect(box!.y+box!.height).toBeLessThan(844);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(failures).toEqual([]);
  await browser.close();
});
