import { test, expect, chromium } from '@playwright/test';
import serverChromium from '@sparticuz/chromium';
const base = process.env.HAYTILE_TEST_URL || 'http://localhost:3000';
// Chromium is delivered through the integrity-checked npm package for this sandbox.
test('real backend: account, draft, private download, handoff, rename, delete and logout', async () => {
  const browser = await chromium.launch({
    executablePath: await serverChromium.executablePath(),
    args: serverChromium.args.filter((a) => a !== '--disable-web-security'),
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript(() => localStorage.setItem('haytile-locale', 'en'));
  await page.goto(base);
  await expect(
    page.getByRole('heading', { name: 'A little imagination. Infinite creation.' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Sign in', exact: true }).first().click();
  await page.getByRole('button', { name: 'Create account', exact: true }).click();
  const dialog = page.getByRole('dialog');
  const email = 'browser-' + Date.now() + '@example.test';
  await dialog.getByLabel('Name', { exact: true }).fill('Browser Creator');
  await dialog.getByLabel('Email', { exact: true }).fill(email);
  await dialog.getByLabel('Password', { exact: true }).fill('Browser-test-password-123');
  await dialog.getByRole('button', { name: 'Create account', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole('button', { name: 'Text Studio', exact: true }).first().click();
  await page.getByLabel('Project title', { exact: true }).fill('My tested story');
  await page
    .getByLabel('Describe your idea', { exact: true })
    .fill('Pawòl mwen rete egzakteman.\nA real saved document.');
  await page.getByRole('button', { name: 'Save draft', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Saved to your library.');
  await page.getByRole('button', { name: 'My Creations', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'My tested story', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Preview My tested story' }).click();
  await expect(page.getByRole('dialog').locator('pre')).toContainText(
    'Pawòl mwen rete egzakteman.',
  );
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('dialog').getByRole('button', { name: 'Download', exact: true }).click(),
  ]);
  expect(download.suggestedFilename()).toBe('My tested story.txt');
  await page.getByRole('dialog').getByRole('button', { name: 'Image Studio' }).click();
  await expect(page.getByLabel('Describe your idea', { exact: true })).toHaveValue(
    'Pawòl mwen rete egzakteman.\nA real saved document.',
  );
  await expect(page.getByRole('button', { name: /^Generate/ })).toBeDisabled();
  await page.getByRole('button', { name: 'My Creations', exact: true }).click();
  await page.getByRole('button', { name: 'Rename', exact: true }).click();
  await page
    .getByRole('dialog')
    .getByRole('textbox', { name: 'Project title' })
    .fill('Renamed story');
  await page.getByRole('dialog').getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('heading', { name: 'Renamed story' })).toBeVisible();
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Delete', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Renamed story' })).not.toBeVisible();
  await page.screenshot({ path: 'test-results/workspace-desktop.png', fullPage: true });
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sign in', exact: true }).first()).toBeVisible();
  expect(errors).toEqual([]);
  // Delete the test account using its known test credentials, no production account involved.
  const login = await page.request.post(base + '/api/v1/auth/login', {
    data: { email, password: 'Browser-test-password-123' },
    headers: { Origin: base },
  });
  const session = await login.json();
  await page.request.delete(base + '/api/v1/me', {
    data: { password: 'Browser-test-password-123' },
    headers: { Authorization: 'Bearer ' + session.token },
  });
  await browser.close();
});
test('mobile viewport, navigation and Arabic direction', async () => {
  const browser = await chromium.launch({
    executablePath: await serverChromium.executablePath(),
    args: serverChromium.args.filter((a) => a !== '--disable-web-security'),
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await page.addInitScript(() => localStorage.setItem('haytile-locale', 'ht'));
  await page.goto(base);
  await expect(page.getByRole('heading', { name: 'Kisa w ap kreye jodi a?' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: 'test-results/workspace-mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'Menu', exact: true }).click();
  await page.getByRole('button', { name: 'Sant èd', exact: true }).first().click();
  await expect(
    page.getByRole('heading', { name: 'Yon ti èd pou pwochen kreyasyon ou' }),
  ).toBeVisible();
  await page.getByRole('combobox', { name: 'Lang', exact: true }).selectOption('ar');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await browser.close();
});

test('saved storyboards retain character identities and exact scene dialogue', async () => {
  const browser = await chromium.launch({
    executablePath: await serverChromium.executablePath(),
    args: serverChromium.args.filter((a) => a !== '--disable-web-security'),
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
  await page.addInitScript(() => localStorage.setItem('haytile-locale', 'en'));
  const email = 'storyboard-' + Date.now() + '@example.test';
  const registered = await page.request.post(base + '/api/v1/auth/register', {
    data: { email, password: 'Storyboard-password-123', name: 'Storyboard Creator', locale: 'en' },
  });
  expect(registered.status()).toBe(201);
  const session = await registered.json();
  await page.goto(base);
  await page.getByRole('button', { name: 'MiniDrama Studio', exact: true }).first().click();
  const editor = page.locator('.storyboard');
  await editor.getByRole('button', { name: 'New project', exact: true }).click();
  await editor.getByLabel('Project title', { exact: true }).fill('My continuity project');
  await editor.getByRole('button', { name: 'Add character', exact: true }).click();
  await editor.getByLabel('Name', { exact: true }).fill('Mika');
  await editor
    .getByLabel('Appearance & personality', { exact: true })
    .fill('Short hair, calm, thoughtful.');
  await editor
    .getByLabel('Clothes & accessories', { exact: true })
    .fill('Blue shirt, silver bracelet.');
  await editor.getByRole('button', { name: 'Add scene', exact: true }).click();
  await editor
    .getByLabel('Exact dialogue script', { exact: true })
    .fill('Bonjou! Pa chanje pawòl mwen.');
  await editor.getByRole('checkbox', { name: 'Mika', exact: true }).check();
  await editor.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(editor.getByRole('status')).toHaveText('Saved to your library.');
  await editor.getByRole('button', { name: 'Reload saved project', exact: true }).click();
  await expect(editor.getByLabel('Exact dialogue script', { exact: true })).toHaveValue(
    'Bonjou! Pa chanje pawòl mwen.',
  );
  const saved = await page.request.get(base + '/api/v1/projects', {
    headers: { Authorization: 'Bearer ' + session.token },
  });
  const projects = await saved.json();
  expect(projects[0].document.scenes[0].character_ids).toContain(
    projects[0].document.characters[0].id,
  );
  await page.request.delete(base + '/api/v1/me', {
    data: { password: 'Storyboard-password-123' },
    headers: { Authorization: 'Bearer ' + session.token },
  });
  await browser.close();
});
