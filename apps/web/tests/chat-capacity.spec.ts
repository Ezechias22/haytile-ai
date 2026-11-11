import {test,expect,chromium} from '@playwright/test';
import serverChromium from '@sparticuz/chromium';

test('successful next message clears an old short-burst banner',async()=>{
 test.skip(process.env.HAYTILE_OFFLINE_CREATIONS!=='1','Offline provider only.');
 const browser=await chromium.launch({executablePath:await serverChromium.executablePath(),args:serverChromium.args.filter(x=>x!=='--disable-web-security'),headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const base=process.env.HAYTILE_TEST_URL||'http://127.0.0.1:8010';
 await page.addInitScript(()=>{if(window.top===window)localStorage.setItem('haytile-locale','en');});
 const login=await page.request.post(base+'/api/v1/auth/login',{data:{email:'creative-browser@example.test',password:'Offline-browser-password-123'},headers:{Origin:base}});expect(login.status()).toBe(200);
 await page.goto(base);await expect(page.locator('.user-line strong')).toHaveText('Creative browser fixture');await page.getByRole('button',{name:'New chat',exact:true}).click();
 let first=true;
 await page.route('**/api/v1/jobs',async route=>{
  if(route.request().method()==='POST'&&first){first=false;await route.fulfill({status:429,json:{detail:'APP_BURST_LIMIT'}});}
  else await route.continue();
 });
 const composer=page.getByRole('textbox',{name:'Your message',exact:true});
 await composer.fill('Continuous chat after a brief guard');
 await page.getByRole('button',{name:'Send message',exact:true}).click();
 // Use the existing localized guard text without depending on its precise punctuation.
 await expect(page.locator('.alert.error')).toBeVisible();
 await expect(page.locator('.alert.error')).not.toContainText('Capacity limit');
 await page.getByRole('button',{name:'Send message',exact:true}).click();
 await expect(page.getByRole('log')).toContainText('Offline reply: Continuous chat after a brief guard',{timeout:20000});
 await expect(page.locator('.alert.error')).toHaveCount(0);
 await browser.close();
});
