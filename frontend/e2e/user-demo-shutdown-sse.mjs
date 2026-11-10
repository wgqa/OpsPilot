import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from '@playwright/test';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const projectRoot = path.resolve(frontendRoot, '..');
const appUrl = process.env.OPSPILOT_TEST_BASE_URL ?? 'http://127.0.0.1:5173';
const expectedSessionId = process.env.OPSPILOT_TEST_EXPECT_SESSION_ID;

function localPassword() {
  const fromProcess = process.env.OPSPILOT_WEB_SUPPORT_PASSWORD;
  if (fromProcess) return fromProcess;
  const envPath = path.join(projectRoot, '.env');
  const match = readFileSync(envPath, 'utf8').match(/^OPSPILOT_WEB_SUPPORT_PASSWORD\s*=\s*(.*)$/m);
  const value = match?.[1]?.trim().replace(/^['"]|['"]$/g, '');
  if (!value || /^(CHANGE_ME|REPLACE_ME|YOUR_)/i.test(value)) {
    throw new Error('Set a private local support password before the browser smoke.');
  }
  return value;
}

const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage();
  await page.goto(appUrl, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('演示身份').selectOption('support-a');
  await page.locator('input[autocomplete="current-password"]').fill(localPassword());
  await page.getByRole('button', { name: /登录工作台/ }).click();
  await page.getByRole('button', { name: '退出' }).waitFor({ timeout: 10_000 });
  if (!expectedSessionId) {
    await page.getByRole('button', { name: '新建会话' }).first().click();
  }

  const sessions = await page.evaluate(async () => {
    const response = await fetch('/api/sessions');
    if (!response.ok) throw new Error(`Session list returned HTTP ${response.status}`);
    return response.json();
  });
  const sessionId = expectedSessionId
    ? sessions.items?.find((item) => item.session_id === expectedSessionId)?.session_id
    : sessions.items?.[0]?.session_id;
  if (!sessionId) throw new Error('The expected persistent Session was not found after login.');
  console.log(`${expectedSessionId ? 'BROWSER_SESSION_PERSISTED' : 'BROWSER_SESSION_CREATED'} ${sessionId}`);

  await page.evaluate((id) => {
    const source = new EventSource(`/api/sessions/${encodeURIComponent(id)}/events?after=0`);
    window.__opspilotShutdownProbe = { source, state: 'CONNECTING' };
    source.onopen = () => { window.__opspilotShutdownProbe.state = 'OPEN'; };
    source.addEventListener('SESSION_CREATED', () => {
      window.__opspilotShutdownProbe.state = 'OPEN_WITH_EVENT';
    });
    source.onerror = () => {
      source.close();
      window.__opspilotShutdownProbe.state = 'CLOSED';
    };
  }, sessionId);
  await page.waitForFunction(
    () => window.__opspilotShutdownProbe?.state === 'OPEN_WITH_EVENT',
    null,
    { timeout: 15_000 },
  );
  console.log('BROWSER_SSE_FIRST_EVENT SESSION_CREATED');
  console.log('BROWSER_SSE_OPEN');

  await page.waitForFunction(
    () => window.__opspilotShutdownProbe?.state === 'CLOSED',
    null,
    { timeout: 35_000 },
  );
  console.log('BROWSER_SSE_CLOSED');
} finally {
  await browser.close();
}
