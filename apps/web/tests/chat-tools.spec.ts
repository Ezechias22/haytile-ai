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
    (window as any).fixtureWatchStarts=0;
    (window as any).fixtureWatchClears=0;
    Object.defineProperty(navigator,'permissions',{value:{query:async()=>({state:localStorage.getItem('fixture-geo-granted')==='yes'?'granted':'prompt',addEventListener(){},removeEventListener(){}})}});
    Object.defineProperty(navigator,'geolocation',{value:{
      getCurrentPosition(success:any,error:any){
        (window as any).fixtureGeoCalls++;
        if((window as any).fixtureGeoCalls===1&&localStorage.getItem('fixture-geo-granted')!=='yes') error({code:1});
        else {localStorage.setItem('fixture-geo-granted','yes');success({timestamp:Date.now(),coords:{latitude:18.543291,longitude:-72.343917,accuracy:8.5}});}
      },
      watchPosition(success:any,_error:any,options:any){
        (window as any).fixtureWatchStarts++;
        (window as any).fixtureHighAccuracy=options.enableHighAccuracy;
        const timer=setTimeout(()=>success({timestamp:Date.now(),coords:{latitude:18.543992,longitude:-72.344112,accuracy:4.5}}),10);
        return timer;
      },
      clearWatch(id:number){clearTimeout(id);(window as any).fixtureWatchClears++;}
    }});

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
  await expect(page.locator('.chat-location-warning')).toContainText('permission denied');
  expect(sent).toHaveLength(2);
  await page.getByRole('button',{name:'Enable location',exact:true}).click();
  await expect(page.getByRole('log')).toContainText('Nearby help found',{timeout:20000});
  expect(sent[2].params.location).toMatchObject({latitude:18.543291,longitude:-72.343917,accuracy_m:8.5});
  await page.getByRole('button',{name:'Web sources 1',exact:true}).click();
  const research=page.getByRole('dialog');
  await expect(research.getByRole('link',{name:/Offline hospital source/})).toHaveAttribute('href','https://example.org/hospital');
  await research.getByRole('button',{name:'Close sources',exact:true}).click();
  await expect(page.getByTitle('Google Search suggestions')).toHaveAttribute('sandbox','allow-popups allow-popups-to-escape-sandbox');
  expect(await page.evaluate(()=>(window as any).fixtureUnsafe)).toBeUndefined();
  const box=await composer.boundingBox();
  expect(box!.y+box!.height).toBeLessThan(844);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.reload();
  await expect(page.getByRole('button',{name:'Stop location sharing',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>(window as any).fixtureGeoCalls)).toBe(0);
  await expect.poll(()=>page.evaluate(()=>(window as any).fixtureWatchStarts)).toBeGreaterThan(0);
  expect(await page.evaluate(()=>(window as any).fixtureHighAccuracy)).toBe(true);
  await expect.poll(async()=>((await page.request.get(base+'/api/v1/chat/location')).json()).then(value=>value.position?.latitude)).toBe(18.543992);
  const countBefore=sent.length;
  await composer.fill('Find nearby offline hospital');
  await page.getByRole('button',{name:'Send message',exact:true}).click();
  await expect.poll(()=>sent.length).toBeGreaterThan(countBefore);
  await expect(page.getByRole('log')).toContainText('Nearby help found',{timeout:20000});
  await expect(page.getByRole('button',{name:'Authorize location',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Stop location sharing',exact:true}).click();
  await expect(page.getByRole('button',{name:'Enable location',exact:true})).toBeVisible();
  await expect.poll(async()=>((await page.request.get(base+'/api/v1/chat/location')).json()).then(value=>value.enabled)).toBe(false);
  await expect.poll(()=>page.evaluate(()=>(window as any).fixtureWatchClears)).toBeGreaterThan(0);
  expect(failures).toEqual([]);
  await browser.close();
});
