import { test, expect, chromium } from '@playwright/test';
import serverChromium from '@sparticuz/chromium';
const base = process.env.HAYTILE_TEST_URL || 'http://127.0.0.1:8010';
async function setup(email = 'creative-browser@example.test') {
  const browser = await chromium.launch({
    executablePath: await serverChromium.executablePath(),
    args: serverChromium.args.filter((x) => x !== '--disable-web-security'),
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.addInitScript(() => localStorage.setItem('haytile-locale', 'en'));
  await page.request.post(base + '/api/v1/auth/login', {
    data: { email, password: 'Offline-browser-password-123' },
    headers: { Origin: base },
  });
  return { browser, page };
}
test('approved offer opens hosted checkout with server offer ID and no client credit grant', async () => {
  test.skip(
    process.env.HAYTILE_OFFLINE_CREATIONS !== '1',
    'Offline UI fixture only. No Stripe transaction.',
  );
  const { browser, page } = await setup();
  const before = await (await page.request.get(base + '/api/v1/wallet')).json();
  let submitted: any = null;
  await page.route('**/api/v1/billing/catalog', (r) =>
    r.fulfill({
      json: {
        available: true,
        has_customer: false,
        test_mode: false,
        offers: [
          {
            id: 'credits-500',
            label: 'Verified Stripe pack',
            credits: 500,
            plan: 'free',
            unit_amount: 500,
            currency: 'usd',
            mode: 'payment',
            interval: '',
          },
        ],
      },
    }),
  );
  await page.route('**/api/v1/billing/checkout', (r) => {
    submitted = r.request().postDataJSON();
    return r.fulfill({ json: { url: 'https://checkout.stripe.com/c/explicit-offline-fixture' } });
  });
  await page.route('https://checkout.stripe.com/**', (r) =>
    r.fulfill({ contentType: 'text/html', body: '<h1>Offline hosted checkout fixture</h1>' }),
  );
  await page.goto(base);
  await page.getByRole('tab', { name: 'Studios', exact: true }).click();
  await page.getByRole('button', { name: 'Credits & plans', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Verified Stripe pack' })).toBeVisible();
  await expect(page.locator('.stripe-payments')).toContainText('$5.00');
  await page.getByRole('button', { name: 'Buy credits', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Offline hosted checkout fixture' }),
  ).toBeVisible();
  expect(submitted.offer_id).toBe('credits-500');
  expect(submitted.idempotency_key).toMatch(/^[a-z0-9-]{36}$/);
  expect(Object.keys(submitted).sort()).toEqual(['idempotency_key', 'offer_id']);
  expect((await (await page.request.get(base + '/api/v1/wallet')).json()).balance).toBe(
    before.balance,
  );
  await browser.close();
});
test('administrator can submit a verified Stripe Price ID and credit mapping', async () => {
  test.skip(process.env.HAYTILE_OFFLINE_CREATIONS !== '1', 'Offline UI fixture only.');
  const { browser, page } = await setup('billing-admin@example.test');
  let offers: any[] = [],
    submitted: any = null;
  await page.route('**/api/v1/admin/billing', (r) =>
    r.fulfill({
      json: {
        key_configured: true,
        webhook_configured: true,
        durable: true,
        live: false,
        ready: true,
        sandbox_balance: 0,
        offers,
        risks: [],
      },
    }),
  );
  await page.route('**/api/v1/admin/billing/offers', (r) => {
    submitted = r.request().postDataJSON();
    offers = [
      {
        ...submitted,
        label: 'Verified Stripe pack',
        unit_amount: 500,
        currency: 'usd',
        mode: 'payment',
        interval: '',
        enabled: 1,
      },
    ];
    return r.fulfill({ json: offers[0] });
  });
  await page.goto(base);
  await page.getByRole('tab', { name: 'Studios', exact: true }).click();
  await page.getByRole('button', { name: 'Administration', exact: true }).click();
  const form = page.locator('.stripe-offer-form');
  await form.getByLabel('Offer ID', { exact: true }).fill('credits-500');
  await form.getByLabel('Stripe Price ID', { exact: true }).fill('price_fixture500');
  await form.getByLabel('credits', { exact: true }).fill('500');
  await form.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page.locator('.stripe-admin .stripe-offers')).toContainText('Verified Stripe pack');
  expect(submitted).toEqual({
    id: 'credits-500',
    price_id: 'price_fixture500',
    credits: 500,
    plan: 'free',
    enabled: true,
  });
  await browser.close();
});

test('return URL waits for an owned server receipt and never grants credits itself', async () => {
  test.skip(process.env.HAYTILE_OFFLINE_CREATIONS !== '1', 'Offline receipt UI fixture only.');
  const { browser, page } = await setup();
  let reads = 0;
  const pid = 'a'.repeat(64);
  const before = await (await page.request.get(base + '/api/v1/wallet')).json();
  await page.route('**/api/v1/billing/catalog', (r) =>
    r.fulfill({ json: { available: true, has_customer: false, test_mode: false, offers: [] } }),
  );
  await page.route('**/api/v1/billing/purchases/' + pid, (r) =>
    r.fulfill({
      json: { status: ++reads >= 2 ? 'paid' : 'pending', test_mode: false, credits: 500 },
    }),
  );
  await page.goto(base + '/?billing=return&purchase_id=' + pid);
  await expect(
    page.getByText(
      'Waiting for payment verification. Returning to this page does not confirm a payment.',
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.getByText(
      'Payment verified by the server. Check the balance and plan below; sandbox payments do not change spendable credits.',
      { exact: true },
    ),
  ).toBeVisible({ timeout: 15000 });
  expect((await (await page.request.get(base + '/api/v1/wallet')).json()).balance).toBe(
    before.balance,
  );
  await browser.close();
});
