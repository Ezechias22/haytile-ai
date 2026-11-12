import {test,expect,chromium} from '@playwright/test';
import serverChromium from '@sparticuz/chromium';

test('rejected music shows provider reason and does not offer blind retry',async()=>{
 test.skip(process.env.HAYTILE_OFFLINE_CREATIONS!=='1','Offline provider only.');
 const browser=await chromium.launch({executablePath:await serverChromium.executablePath(),args:serverChromium.args.filter(x=>x!=='--disable-web-security'),headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const base=process.env.HAYTILE_TEST_URL||'http://127.0.0.1:8010';
 await page.addInitScript(()=>localStorage.setItem('haytile-locale','en'));
 const login=await page.request.post(base+'/api/v1/auth/login',{data:{email:'creative-browser@example.test',password:'Offline-browser-password-123'},headers:{Origin:base}});expect(login.status()).toBe(200);
 await page.goto(base);await expect(page.locator('.user-line strong')).toHaveText('Creative browser fixture');
 const before=await (await page.request.get(base+'/api/v1/wallet')).json();
 await page.getByRole('tab',{name:'Studios',exact:true}).click();await page.getByRole('button',{name:'Music Studio',exact:true}).first().click();
 await page.getByLabel('Lyrics or song idea',{exact:true}).fill('Offline rejected music: a song for peace.');
 await page.getByRole('button',{name:/^Generate/}).click();await page.getByRole('dialog').getByRole('button',{name:'Confirm',exact:true}).click();
 const activity=page.getByRole('region',{name:'Generation activity',exact:true});
 await expect(activity).toContainText('The provider applied its content rules',{timeout:20000});
 await expect(activity.getByRole('button',{name:'Retry',exact:true})).toHaveCount(0);
 await activity.getByText('Error details',{exact:true}).click();
 await expect(activity).toContainText('Input blocked: The prompt could not be processed.');
 await expect(activity).toContainText('PROVIDER_CONTENT_REJECTED');
 const id=await activity.locator('[data-job-id]').getAttribute('data-job-id');
 const blocked=await page.request.post(base+'/api/v1/jobs/'+id+'/retry',{data:{},headers:{Origin:base}});expect(blocked.status()).toBe(409);
 const after=await (await page.request.get(base+'/api/v1/wallet')).json();expect(after.balance).toBe(before.balance);expect(after.reserved).toBe(0);
 await page.setViewportSize({width:390,height:844});await activity.scrollIntoViewIfNeeded();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:'test-results/music-provider-rejection-mobile.png',fullPage:true});await browser.close();
});
