import {test, expect, chromium} from '@playwright/test';
import serverChromium from '@sparticuz/chromium';

test('interrupted chat distinguishes an explicit new request from result recovery', async()=>{
 test.skip(process.env.HAYTILE_OFFLINE_CREATIONS!=='1','Offline provider only.');
 const browser=await chromium.launch({executablePath:await serverChromium.executablePath(),args:serverChromium.args.filter(x=>x!=='--disable-web-security'),headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const base=process.env.HAYTILE_TEST_URL||'http://127.0.0.1:8010';
 await page.addInitScript(()=>{if(window.top===window)localStorage.setItem('haytile-locale','en');});
 const login=await page.request.post(base+'/api/v1/auth/login',{data:{email:'creative-browser@example.test',password:'Offline-browser-password-123'},headers:{Origin:base}});expect(login.status()).toBe(200);
 await page.goto(base);await expect(page.locator('.user-line strong')).toHaveText('Creative browser fixture');
 await page.getByRole('button',{name:'New chat',exact:true}).click();
 await page.getByRole('textbox',{name:'Your message',exact:true}).fill('Offline interrupted reply');
 await page.getByRole('button',{name:'Send message',exact:true}).click();
 const failure=page.locator('.chat-failure');
 await expect(failure).toContainText('Sending again creates a new request.',{timeout:20000});
 await expect(failure.getByRole('button',{name:'Retry',exact:true})).toHaveCount(0);
 const response=page.waitForRequest(request=>request.method()==='POST'&&request.url().endsWith('/retry'));
 await failure.getByRole('button',{name:'Send a new request',exact:true}).click();
 expect((await response).postDataJSON()).toEqual({new_request:true});
 await expect(page.getByRole('log')).toContainText('Offline reply: Offline interrupted reply',{timeout:20000});
 await expect(failure).toHaveCount(0);
 await browser.close();
});

test('preparation failure is safely retryable without a new-request confirmation', async()=>{
 test.skip(process.env.HAYTILE_OFFLINE_CREATIONS!=='1','Offline provider only.');
 const browser=await chromium.launch({executablePath:await serverChromium.executablePath(),args:serverChromium.args.filter(x=>x!=='--disable-web-security'),headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const base=process.env.HAYTILE_TEST_URL||'http://127.0.0.1:8010';
 await page.addInitScript(()=>{if(window.top===window)localStorage.setItem('haytile-locale','en');});
 const login=await page.request.post(base+'/api/v1/auth/login',{data:{email:'creative-browser@example.test',password:'Offline-browser-password-123'},headers:{Origin:base}});expect(login.status()).toBe(200);
 await page.goto(base);await expect(page.locator('.user-line strong')).toHaveText('Creative browser fixture');await page.getByRole('button',{name:'New chat',exact:true}).click();
 const armed=await page.request.post(base+'/api/v1/offline/prepare-import-failure',{headers:{Origin:base}});expect(armed.status()).toBe(200);
 await page.getByRole('textbox',{name:'Your message',exact:true}).fill('Offline preparation failure');
 await page.getByRole('button',{name:'Send message',exact:true}).click();
 const failure=page.locator('.chat-failure');
 await expect(failure).toContainText('before contacting the AI',{timeout:20000});
 await expect(failure.getByRole('button',{name:'Send a new request',exact:true})).toHaveCount(0);
 await failure.locator('summary').click();await expect(failure).toContainText('ImportError');
 const response=page.waitForRequest(request=>request.method()==='POST'&&request.url().endsWith('/retry'));
 await failure.getByRole('button',{name:'Retry',exact:true}).click();expect((await response).postData()).toBeNull();
 await expect(page.getByRole('log')).toContainText('Offline reply: Offline preparation failure',{timeout:20000});
 await expect(failure).toHaveCount(0);await browser.close();
});
