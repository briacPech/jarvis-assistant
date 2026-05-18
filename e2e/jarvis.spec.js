// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('Jarvis Chat', () => {
  test('API et page chat chargent', async ({ request, page }) => {
    const api = await request.get('/api');
    expect(api.ok()).toBeTruthy();
    const body = await api.json();
    expect(body.name || body.status).toBeTruthy();

    await page.goto('/');
    await expect(page.locator('h1')).toHaveText(/Jarvis/i);
    await expect(page.locator('#text')).toBeVisible();
    await expect(page.locator('#sendBtn')).toBeVisible();
    await expect(page.locator('#streamCheck')).toBeChecked();
  });

  test('chat JSON rapide sans voix', async ({ request }) => {
    const r = await request.post(
      '/chat?message=Dis%20bonjour%20en%20une%20phrase&speak=false&web=false&brief=true',
      { timeout: 90000 }
    );
    expect(r.ok()).toBeTruthy();
    const data = await r.json();
    expect((data.response || '').length).toBeGreaterThan(2);
  });

  test('rappel memoire sans timeout LLM', async ({ request }) => {
    const r = await request.post(
      '/chat?message=rappelle-moi%20ce%20que%20tu%20sais%20sur%20moi&speak=false&web=false',
      { timeout: 15000 }
    );
    expect(r.ok()).toBeTruthy();
    const data = await r.json();
    expect(data.memory_recall || data.route === 'memory_facts' || (data.response || '').includes('retiens')).toBeTruthy();
    expect((data.response || '').length).toBeGreaterThan(10);
  });

  test('stream SSE termine (chemin simple)', async ({ request }) => {
    const r = await request.post(
      '/chat/stream?message=salut&speak=false&web=false&brief=true',
      { timeout: 120000 }
    );
    expect(r.ok()).toBeTruthy();
    const text = await r.text();
    expect(text).toMatch(/data:\s*\{/);
    expect(text).toMatch(/"done"\s*:\s*true/);
    expect(text.length).toBeGreaterThan(20);
  });
});
