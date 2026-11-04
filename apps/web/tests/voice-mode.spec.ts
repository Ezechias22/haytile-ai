import { test, expect, chromium } from '@playwright/test';
import serverChromium from '@sparticuz/chromium';

test('voice session: selected voice, automatic paid replies, budget, separate navigation and deletion', async () => {
  test.skip(process.env.HAYTILE_OFFLINE_CREATIONS !== '1', 'Requires explicit offline provider.');
  const browser = await chromium.launch({ executablePath: await serverChromium.executablePath(), args: serverChromium.args.filter(x => x !== '--disable-web-security'), headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, reducedMotion: 'reduce' });
  const failures: string[] = [], jobs: any[] = [];
  page.on('pageerror', error => failures.push(error.message));
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/api/v1/jobs')) jobs.push(request.postDataJSON()); });
  await page.addInitScript(() => {
    localStorage.setItem('haytile-locale','en');
    (window as any).SpeechRecognition = class {
      onresult: any; onend: any; onerror: any;
      start() { (window as any).__voiceRecognition = this; }
      abort() {}
      stop() { this.onend?.(); }
    };
  });
  const base = process.env.HAYTILE_TEST_URL || 'http://127.0.0.1:3010';
  await page.request.post(base + '/api/v1/auth/login', { data: { email: 'creative-browser@example.test', password: 'Offline-browser-password-123' }, headers: { Origin: base } });
  const before = await (await page.request.get(base + '/api/v1/wallet')).json();
  await page.goto(base);
  await expect(page.getByRole('button',{name:'New chat',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'New chat',exact:true}).click();
  const toggle = page.getByRole('button',{name:'Toggle sidebar',exact:true});
  await toggle.click(); await expect(toggle).toHaveAttribute('aria-expanded','false');
  await expect(page.locator('.sidebar')).not.toBeVisible();
  await toggle.click(); await expect(toggle).toHaveAttribute('aria-expanded','true');
  await expect(page.getByRole('button',{name:'Music Studio',exact:true})).toHaveCount(0);
  await page.getByRole('tab',{name:'Studios',exact:true}).click();
  await expect(page.getByRole('button',{name:'Music Studio',exact:true})).toBeVisible();
  await expect(page.locator('.sidebar-chat-history')).toHaveCount(0);
  await page.getByRole('tab',{name:'Chats',exact:true}).click();
  await page.getByRole('combobox',{name:'Reply voice',exact:true}).selectOption('Charon');
  await expect(page.getByRole('combobox',{name:'Voice model',exact:true})).toHaveValue('offline-voice-model');
  await page.getByRole('button',{name:'Start voice conversation',exact:true}).click();
  const approval = page.getByRole('group',{name:'Approve voice session',exact:true});
  await expect(approval).toContainText('3 credits');
  await approval.getByRole('spinbutton',{name:'Session credit budget',exact:true}).fill('6');
  const started = page.waitForResponse(response => response.url().endsWith('/api/v1/chat/voice-sessions') && response.request().method() === 'POST');
  await approval.getByRole('button',{name:'Approve budget and start',exact:true}).click();
  const session = await (await started).json();
  const say = async (text: string) => {
    await expect.poll(() => page.evaluate(() => !!(window as any).__voiceRecognition?.onresult)).toBe(true);
    await page.evaluate(text => { const r=(window as any).__voiceRecognition; r.onresult({results:[[{transcript:text}]]}); r.onend?.(); }, text);
  };
  await say('Natural voice one');
  const audio = page.getByLabel('Voice conversation audio',{exact:true});
  await expect(audio).toHaveAttribute('src',/\/api\/v1\/files\//,{timeout:30000});
  await expect.poll(() => audio.evaluate((element: HTMLAudioElement) => element.played.length)).toBeGreaterThan(0);
  await expect(page.getByText('Listening… speak naturally',{exact:true})).toBeVisible({timeout:10000});
  await page.screenshot({path:'test-results/natural-voice-mode.png',fullPage:true});
  await say('Natural voice two');
  await expect(page.getByRole('button',{name:'End voice conversation',exact:true})).toHaveCount(0,{timeout:30000});
  await expect(page.locator('.credit-pill')).toContainText(String(before.balance-6));
  const voiceJobs = jobs.filter(job => job.studio==='voice');
  expect(voiceJobs).toHaveLength(2);
  expect(voiceJobs.every(job => job.params.voice_name==='Charon' && job.model_id==='offline-voice-model' && job.params.voice_session_id===session.id)).toBe(true);
  expect(jobs.filter(job=>job.studio==='text').every(job=>job.model_id==='offline-chat-model' && job.confirmed_credits===0)).toBe(true);
  const ended=await (await page.request.get(base+'/api/v1/chat/voice-sessions/'+session.id)).json();
  expect(ended.remaining).toBe(0);
  await page.getByRole('button',{name:'Delete conversation Natural voice one',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Delete',exact:true}).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByRole('button',{name:'Delete conversation Natural voice one',exact:true})).toHaveCount(0);
  expect(await (await page.request.get(base+'/api/v1/chat/conversations/'+session.conversation_id)).json()).toEqual([]);
  expect((await (await page.request.get(base+'/api/v1/wallet')).json()).balance).toBe(before.balance-6);
  expect(failures).toEqual([]);
  await browser.close();
});
