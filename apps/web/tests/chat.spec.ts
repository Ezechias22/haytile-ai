import { test, expect, chromium } from '@playwright/test';
import serverChromium from '@sparticuz/chromium';

test('offline chat: identity, replies in place, context and persisted history', async () => {
  test.skip(process.env.HAYTILE_OFFLINE_CREATIONS !== '1', 'Requires explicit offline provider.');
  const browser = await chromium.launch({ executablePath: await serverChromium.executablePath(), args: serverChromium.args.filter(x => x !== '--disable-web-security'), headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  const failures: string[] = [];
  page.on('pageerror', error => failures.push(error.message));
  await page.addInitScript(() => {
    localStorage.setItem('haytile-locale', 'en');
    (window as any).SpeechRecognition = class {
      onresult: any; onend: any;
      start() { setTimeout(() => { this.onresult?.({ results: [[{ transcript: 'Who are you? Remember the word mango.' }]] }); this.onend?.(); }, 30); }
      stop() { this.onend?.(); }
      abort() {}
    };
  });
  await page.goto(process.env.HAYTILE_TEST_URL || 'http://127.0.0.1:3010');
  await expect(page.getByRole('heading', { name: 'Hello, I’m HAYTILE AI' })).toBeVisible();
  await page.getByRole('button', { name: 'Sign in', exact: true }).first().click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Email', { exact: true }).fill('creative-browser@example.test');
  await dialog.getByLabel('Password', { exact: true }).fill('Offline-browser-password-123');
  await dialog.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole('button', { name: 'HAYTILE Chat', exact: true }).click();
  await page.getByRole('button', { name: 'New chat', exact: true }).click();
  const composer = page.getByRole('textbox', { name: 'Your message', exact: true });
  await page.getByRole('button', { name: 'Dictate a message', exact: true }).click();
  await expect(composer).toHaveValue('Who are you? Remember the word mango.');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  const log = page.getByRole('log', { name: 'Conversation' });
  await expect(log).toContainText('I am HAYTILE AI. Offline reply:', { timeout: 20000 });
  await expect(log).toContainText('Previous messages: 0');
  await log.getByRole('button', { name: 'Generate voice reply', exact: true }).click();
  const consent = log.getByRole('group', { name: 'Confirm generation cost' });
  await expect(consent).toContainText('3');
  await page.getByRole('combobox', { name: 'Reply voice', exact: true }).selectOption('Kore');
  await expect(consent).toHaveCount(0);
  await page.getByRole('combobox', { name: 'Reply voice', exact: true }).selectOption('Puck');
  await log.getByRole('button', { name: 'Generate voice reply', exact: true }).click();
  await expect(consent).toContainText('3');
  await consent.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(log.locator('audio')).toHaveAttribute('src', /\/api\/v1\/files\//, { timeout: 20000 });
  await expect(page.locator('.credit-pill')).toContainText('47');

  await composer.fill('What word did I ask you to remember?');
  await composer.press('Enter');
  await expect(log).toContainText('Previous messages: 2', { timeout: 20000 });
  await expect(page.getByRole('button', { name: 'Text Studio', exact: true })).toHaveCount(0);
  await page.getByRole('tab', { name: 'Studios', exact: true }).click();
  await page.getByRole('button', { name: 'My Creations', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'My Creations', exact: true })).toBeVisible();
  await expect(page.locator('.asset-grid').getByRole('heading', { name: 'Who are you? Remember the word mango.', exact: true })).toHaveCount(0);
  await expect(page.locator('.creation-live')).toHaveCount(0);
  await page.getByRole('tab', { name: 'Chats', exact: true }).click();
  const history = page.locator('.sidebar-chat-history');
  await expect(history).toContainText('Who are you?');
  await history.getByRole('button', { name: 'Who are you? Remember the word mango.', exact: true }).click();
  await expect(page.getByRole('log')).toContainText('Previous messages: 2');
  await page.getByRole('tab', { name: 'Studios', exact: true }).click();
  await page.getByRole('button', { name: 'Voice Studio', exact: true }).click();
  await page.getByRole('button', { name: 'Male voices', exact: true }).click();
  const voices = page.getByRole('combobox', { name: 'Choose a voice', exact: true });
  await expect(voices).toHaveValue('Puck');
  await expect(voices.locator('option[value="Puck"]')).toHaveText('Puck · Male');
  await expect(voices.locator('option[value="Kore"]')).toHaveCount(0);
  await page.getByRole('tab', { name: 'Chats', exact: true }).click();
  await history.getByRole('button', { name: 'Who are you? Remember the word mango.', exact: true }).click();
  await page.reload();
  await expect(page.getByRole('log')).toContainText('Previous messages: 2');
  await expect(page.getByRole('log').locator('audio')).toHaveAttribute('src', /\/api\/v1\/files\//);
  await page.screenshot({ path: 'test-results/chat-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: 'test-results/chat-mobile.png', fullPage: true });
  expect(failures).toEqual([]);
  await browser.close();
});

test('offline paid images: exact quote and a real wallet debit after completion', async () => {
  test.skip(process.env.HAYTILE_OFFLINE_CREATIONS !== '1', 'Requires explicit offline provider.');
  const browser = await chromium.launch({ executablePath: await serverChromium.executablePath(), args: serverChromium.args.filter(x => x !== '--disable-web-security'), headless: true });
  const page = await browser.newPage();
  await page.addInitScript(() => localStorage.setItem('haytile-locale', 'en'));
  const base = process.env.HAYTILE_TEST_URL || 'http://127.0.0.1:3010';
  const login = await page.request.post(base + '/api/v1/auth/login', { data: { email: 'creative-browser@example.test', password: 'Offline-browser-password-123' }, headers: { Origin: base } });
  expect(login.status()).toBe(200);
  const before = await (await page.request.get(base + '/api/v1/wallet')).json();
  await page.goto(base);
  await page.getByRole('tab', { name: 'Studios', exact: true }).click();
  await page.getByRole('button', { name: 'Image Studio', exact: true }).click();
  await page.getByRole('textbox', { name: 'Describe your idea', exact: true }).fill('An offline purple garden image');
  const generate = page.getByRole('button', { name: 'Generate 8 credits', exact: true });
  await expect(generate).toBeEnabled();
  await generate.click();
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'My Creations', exact: true })).toBeVisible();
  await expect(page.locator('.credit-pill')).toContainText(String(before.balance - 8));
  await expect(page.locator('.creation-live')).toContainText('Your file is ready', { timeout: 20000 });
  const after = await (await page.request.get(base + '/api/v1/wallet')).json();
  expect(after.balance).toBe(before.balance - 8);
  expect(after.reserved).toBe(0);
  await browser.close();
});
