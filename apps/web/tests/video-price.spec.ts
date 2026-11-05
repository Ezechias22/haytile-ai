import { test, expect, chromium } from '@playwright/test';
import serverChromium from '@sparticuz/chromium';

test('video price distinguishes each clip from the full duration quote', async () => {
  test.skip(process.env.HAYTILE_OFFLINE_CREATIONS !== '1', 'Requires the local offline account.');
  const browser = await chromium.launch({ executablePath: await serverChromium.executablePath(), args: serverChromium.args.filter(x => x !== '--disable-web-security'), headless: true });
  try {
    const page = await browser.newPage();
    const base = process.env.HAYTILE_TEST_URL || 'http://127.0.0.1:8010';
    await page.addInitScript(() => localStorage.setItem('haytile-locale', 'en'));
    const login = await page.request.post(base + '/api/v1/auth/login', { data: { email: 'creative-browser@example.test', password: 'Offline-browser-password-123' }, headers: { Origin: base } });
    expect(login.status()).toBe(200);
    await page.route('**/api/v1/models', route => route.fulfill({ json: [{ studio: 'video', available: true, model_id: 'gemini-omni-1.1-flash', credits: 168, options: [{ model_id: 'gemini-omni-1.1-flash', label: 'Gemini Omni 1.1 Flash', credits: 168, available: true }] }] }));
    await page.route('**/api/v1/quotes', route => route.fulfill({ json: { credits: 3864, clip_count: 23, free: false } }));
    let generations = 0;
    page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/api/v1/jobs')) generations++; });
    await page.goto(base);
    await page.getByRole('tab', { name: 'Studios', exact: true }).click();
    await page.getByRole('button', { name: 'Video Studio', exact: true }).click();
    await expect(page.getByRole('combobox', { name: 'AI model', exact: true }).locator('option:checked')).toContainText('168 credits / clip');
    await page.getByRole('textbox', { name: 'Describe your idea', exact: true }).fill('A continuous music video');
    await page.getByRole('button', { name: '3 min', exact: true }).click();
    await expect(page.getByRole('button', { name: /Generate.*3864/ })).toBeVisible();
    await expect(page.getByRole('status').filter({ hasText: 'Total price' })).toContainText('23');
    await expect(page.getByRole('status').filter({ hasText: 'Total price' })).toContainText('3864 credits');
    expect(generations).toBe(0);
  } finally { await browser.close(); }
});
