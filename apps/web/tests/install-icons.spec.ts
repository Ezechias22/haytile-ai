import { test, expect, chromium } from '@playwright/test';
import serverChromium from '@sparticuz/chromium';

test('installed web app resolves the branded Android and Apple icons', async () => {
  test.skip(process.env.HAYTILE_ICON_CHECK !== '1', 'Explicit read-only icon verification.');
  const browser = await chromium.launch({ executablePath: await serverChromium.executablePath(), args: serverChromium.args.filter(x => x !== '--disable-web-security'), headless: true });
  try {
    const page = await browser.newPage();
    const base = process.env.HAYTILE_TEST_URL || 'http://127.0.0.1:8010';
    await page.goto(base);
    const manifestPath = await page.locator('link[rel="manifest"]').getAttribute('href');
    expect(manifestPath).toBeTruthy();
    const session = await page.context().newCDPSession(page);
    const parsed = await session.send('Page.getAppManifest');
    expect(parsed.errors).toEqual([]);
    if (!parsed.data) throw new Error('The browser did not discover an install manifest.');
    const manifest = JSON.parse(parsed.data);
    expect(manifest.name).toBe('HAYTILE AI');
    expect(manifest.display).toBe('standalone');
    expect(manifest.start_url).toBe('/');
    expect(manifest.icons).toEqual(expect.arrayContaining([
      expect.objectContaining({ sizes: '192x192', purpose: 'any' }),
      expect.objectContaining({ sizes: '512x512', purpose: 'any' }),
      expect.objectContaining({ sizes: '512x512', purpose: 'maskable' }),
    ]));
    for (const icon of manifest.icons) {
      const dimensions = await page.evaluate(async path => {
        const image = new Image(); image.src = path; await image.decode();
        return `${image.naturalWidth}x${image.naturalHeight}`;
      }, icon.src);
      expect(dimensions).toBe(icon.sizes);
    }
    const apple = page.locator('link[rel="apple-touch-icon"]');
    await expect(apple).toHaveAttribute('href', '/icons/apple-touch-icon-v1.png');
    const response = await page.request.get(new URL('/icons/apple-touch-icon-v1.png', base).href);
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toContain('image/png');
    await expect(page.locator('link[rel="icon"][href="/favicon.svg"]')).toHaveCount(0);
  } finally { await browser.close(); }
});
