import { test, expect, chromium } from '@playwright/test';
import serverChromium from '@sparticuz/chromium';

test('private admin: activate, search user, grant credits and assign expiring plan', async () => {
  const email = process.env.HAYTILE_TEST_ADMIN_EMAIL;
  const code = process.env.HAYTILE_TEST_ADMIN_CODE;
  test.skip(
    !email || !code,
    'Requires a local-only operator activation fixture, never production secrets.',
  );
  const browser = await chromium.launch({
    executablePath: await serverChromium.executablePath(),
    args: serverChromium.args.filter((a) => a !== '--disable-web-security'),
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const base = process.env.HAYTILE_TEST_URL || 'http://localhost:3000';
  const recipient = `admin-recipient-${Date.now()}@example.test`;
  const password = 'Browser-local-fixture-password-123';
  const headers = { Origin: base };
  for (const account of [email!, recipient]) {
    const response = await page.request.post(base + '/api/v1/auth/register', {
      headers,
      data: { email: account, password, name: 'Admin browser fixture', locale: 'en' },
    });
    expect([201, 409]).toContain(response.status());
  }
  await page.request.post(base + '/api/v1/auth/logout', { headers });
  await page.addInitScript(() => localStorage.setItem('haytile-locale', 'en'));
  await page.goto(base);
  await page.getByRole('button', { name: 'Sign in', exact: true }).first().click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Email', { exact: true }).fill(email!);
  await dialog.getByLabel('Password', { exact: true }).fill(password);
  await dialog.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await page.getByRole('button', { name: 'Settings', exact: true }).first().click();
  const activation = page.getByLabel('Private activation code', { exact: true });
  if (await activation.count()) {
    await activation.fill(code!);
    await page.getByRole('button', { name: 'Activate administrator access', exact: true }).click();
  }
  await page.getByRole('button', { name: 'Administration', exact: true }).click();
  const section = page
    .locator('section')
    .filter({ has: page.getByRole('heading', { name: 'Manage users', exact: true }) });
  await section.getByLabel('Search users', { exact: true }).fill(recipient);
  await section.getByRole('button', { name: recipient, exact: true }).click();
  await section.getByLabel('Amount', { exact: true }).fill('25');
  await section.getByRole('button', { name: 'Grant credits', exact: true }).click();
  const row = section.locator('tbody tr').filter({ hasText: recipient });
  await expect(row).toContainText('25');
  await section.getByLabel('Plan', { exact: true }).selectOption('creator');
  await section.getByLabel('One-time credits', { exact: true }).fill('10');
  await section.getByLabel('Reason', { exact: true }).fill('Browser verified manual gift');
  await section.getByRole('button', { name: 'Assign plan', exact: true }).click();
  await expect(row).toContainText('35');
  await expect(row).toContainText('creator');
  await page.screenshot({ path: 'test-results/admin-management.png', fullPage: true });
  await browser.close();
});
