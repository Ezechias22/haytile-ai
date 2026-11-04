import { test, expect, chromium } from '@playwright/test';
import serverChromium from '@sparticuz/chromium';

test('offline provider: auto-title, consent, My Creations, live stages, rename and playable result', async () => {
  test.skip(
    process.env.HAYTILE_OFFLINE_CREATIONS !== '1',
    'Requires the isolated offline API/worker, never a paid provider.',
  );
  const base = process.env.HAYTILE_TEST_URL || 'http://127.0.0.1:3010';
  const browser = await chromium.launch({
    executablePath: await serverChromium.executablePath(),
    args: serverChromium.args.filter((x) => x !== '--disable-web-security'),
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const failures: string[] = [];
  page.on('pageerror', (e) => failures.push(e.message));
  await page.addInitScript(() => localStorage.setItem('haytile-locale', 'en'));
  await page.goto(base);
  await page.getByRole('button', { name: 'Sign in', exact: true }).first().click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Email', { exact: true }).fill('creative-browser@example.test');
  await dialog.getByLabel('Password', { exact: true }).fill('Offline-browser-password-123');
  await dialog.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  const initialWallet = await (await page.request.get(base + '/api/v1/wallet')).json();
  await page.getByRole('button', { name: 'Music Studio', exact: true }).first().click();
  await page
    .getByLabel('Describe your idea', { exact: true })
    .fill('Tit: Lakay Nan Kè Mwen\nAn offline browser fixture, not a paid music request.');
  await expect(page.getByLabel('Project title', { exact: true })).toHaveValue('Lakay Nan Kè Mwen');
  await page.getByRole('button', { name: /^Generate/ }).click();
  await expect(page.getByRole('dialog')).toContainText('12');
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'My Creations', exact: true })).toBeVisible();
  const live = page.getByRole('region', { name: 'Generation activity', exact: true });
  await expect(live.getByRole('heading', { name: 'Lakay Nan Kè Mwen', exact: true })).toBeVisible();
  await expect(live.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '15', {
    timeout: 10000,
  });
  await live.getByRole('button', { name: 'Rename Lakay Nan Kè Mwen', exact: true }).click();
  await page
    .getByRole('dialog')
    .getByLabel('Project title', { exact: true })
    .fill('Mizik mwen renome');
  await page.getByRole('dialog').getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(live.getByRole('heading', { name: 'Mizik mwen renome', exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/creation-progress-live.png', fullPage: true });
  await expect(live).toContainText('Your file is ready', { timeout: 20000 });
  await expect(page.locator('.credit-pill')).toContainText(String(initialWallet.balance - 12));
  await expect(page.locator('.asset-grid')).toContainText('Mizik mwen renome');
  await live.getByRole('button', { name: 'Preview', exact: true }).click();
  const audio = page.getByRole('dialog').locator('audio');
  await expect(audio).toHaveAttribute('src', /\/api\/v1\/files\//);
  await expect
    .poll(() => audio.evaluate((el: HTMLAudioElement) => el.readyState))
    .toBeGreaterThanOrEqual(2);
  await page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
  await page.screenshot({ path: 'test-results/creations-mobile-ready.png', fullPage: true });
  expect(failures).toEqual([]);
  await browser.close();
});
