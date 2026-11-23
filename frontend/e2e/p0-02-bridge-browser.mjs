import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium, expect } from '@playwright/test';

const origin = process.env.OPSPILOT_BRIDGE_ORIGIN ?? 'http://127.0.0.1:8875';
const output = process.env.OPSPILOT_BRIDGE_BROWSER_OUTPUT;
if (!output) throw new Error('OPSPILOT_BRIDGE_BROWSER_OUTPUT is required');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
const responses = [];
page.on('response', (response) => {
  const pathname = new URL(response.url()).pathname;
  if (pathname.startsWith('/api/')) responses.push({ path: pathname, status: response.status(), method: response.request().method() });
});
const sourceTexts = ['Only event E7', 'Use protocol v2', 'Time window 10:00-11:00', 'Report receiver status separately'];
const panel = page.getByTestId('condition-review');
let task = '';
let persistedReceipt;

async function send(text) {
  const box = page.getByTestId('message-input');
  await expect(box).toBeEnabled();
  await box.fill(text);
  await page.getByRole('button', { name: '发送消息' }).click();
  await expect(box).toBeEnabled({ timeout: 25_000 });
}

try {
  await page.goto(origin);
  await page.getByLabel('演示身份').selectOption('support-a');
  await page.getByLabel('本地口令').fill('p002-browser-fixture');
  await page.getByRole('button', { name: '登录工作台' }).click();
  await expect(page.locator('.rail-footer')).toContainText('support-a');
  await page.locator('.new-session-button').click();
  await page.getByTestId('assistant-order-open').click();
  await page.getByTestId('assistant-order-resource').selectOption('p002-order');
  await page.getByTestId('assistant-order-question').fill('Investigate the callback');
  const bound = page.waitForResponse((response) => response.url().endsWith('/assistant/order') && response.status() === 202);
  await page.getByRole('button', { name: '确认订单并调查' }).click();
  task = (await (await bound).json()).task_id;
  for (const text of sourceTexts) await send(text);
  await send('按照之前的四项条件继续调查。');
  await expect(panel).toHaveCount(0);
  await page.getByTestId('condition-review-toggle').click();
  const discovered = page.waitForResponse((response) => response.url().endsWith('/condition-review')
    && response.request().method() === 'POST' && response.status() === 200);
  await page.getByTestId('condition-review-discover').click();
  const recovered = (await (await discovered).json()).review.candidates;
  await expect(panel.getByTestId('condition-candidate')).toHaveCount(4);
  for (const text of sourceTexts) await expect(panel).toContainText(text);
  for (const source of recovered) {
    const candidate = panel.getByTestId('condition-candidate').filter({ hasText: source.source_text });
    await expect(candidate).toContainText(`第 ${source.sequence} 条消息`);
  }
  await page.screenshot({ path: path.join(output, '01-candidates.png') });

  await page.reload();
  await expect(panel.getByTestId('condition-candidate')).toHaveCount(4);
  await expect(panel.getByTestId('condition-review-confirm')).toBeDisabled();
  for (const checkbox of await panel.getByRole('checkbox').all()) await checkbox.check();
  await page.route('**/condition-review/*/confirm', async (route) => {
    const upstream = await route.fetch();
    if (upstream.status() !== 200) throw new Error(`Confirm returned ${upstream.status()}`);
    persistedReceipt = await upstream.json();
    await route.abort('failed'); // The server committed successfully; response never reached the UI.
  });
  await panel.getByTestId('condition-review-confirm').click();
  await expect(panel.getByTestId('condition-review-status')).toContainText(/已确认|已应用/);
  await page.unroute('**/condition-review/*/confirm');
  await page.reload();
  await expect(panel.getByTestId('condition-review-status')).toContainText('已应用到后续调查');
  await expect(panel.getByRole('list', { name: '当前生效条件' }).locator('li')).toHaveCount(4);
  await page.screenshot({ path: path.join(output, '02-applied-after-reload.png') });
  const result = await page.evaluate(async (taskId) => {
    const response = await fetch(`/api/tasks/${taskId}/condition-review`);
    return response.json();
  }, task);
  expect(result.review.run_id).toBe(persistedReceipt.run_id);
  await page.getByTestId('condition-review-toggle').click();
  await expect(page.getByTestId('assistant-critical-correction')).toBeVisible();
  await send('HTTP 202 是什么意思？');
  await expect(page.getByText('HTTP 202 表示请求已被接受处理；处理结果仍待确认。')).toBeVisible();
  await expect(panel).toHaveCount(0);
  expect(responses.filter((item) => item.method === 'POST' && item.path.endsWith('/condition-review'))).toHaveLength(1);
  await page.screenshot({ path: path.join(output, '03-ordinary-chat.png') });
  await writeFile(path.join(output, 'browser-results.json'), JSON.stringify({ task, receipt: persistedReceipt, result, responses }, null, 2));
  console.log('Browser verified four sourced candidates, dropped confirmation response, reload and ordinary chat.');
} catch (error) {
  await page.screenshot({ path: path.join(output, 'failure.png') });
  await writeFile(path.join(output, 'browser-failure.json'), JSON.stringify({ error: String(error), responses }, null, 2));
  throw error;
} finally {
  await browser.close();
}
