import { spawn } from 'node:child_process';
import path from 'node:path';
import { chromium, expect } from '@playwright/test';

const baseURL = 'http://127.0.0.1:5189';
const vite = spawn(process.execPath, [
  path.resolve('node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5189', '--strictPort',
], { cwd: process.cwd(), windowsHide: true, stdio: 'ignore' });
let browser;

const sessions = [
  { session_id: 'session-b-c01-a', created_at: '2026-11-10T00:00:00Z', updated_at: '2026-11-10T00:01:00Z', task_count: 0 },
];
const messageCounts = { 'session-a-c01-a': 1200, 'session-b-c01-a': 1 };

function message(sessionId, sequence) {
  return {
    message_id: `${sessionId}-message-${sequence}`,
    session_id: sessionId,
    task_id: null,
    sequence,
    role: 'USER',
    input_kind: 'CHAT_READONLY',
    body: sessionId === 'session-b-c01-a' ? 'SESSION_B_ONLY_MESSAGE' : `session-a-message-${sequence}`,
    created_at: '2026-11-10T00:00:00Z',
    command_id: `${sessionId}-command-${sequence}`,
    application_state: null,
    applied_run_id: null,
    investigation_origin_message_id: null,
    answer_run_id: null,
    answer_source_message_id: null,
    answer_kind: null,
  };
}

async function installApiMocks(page) {
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const parts = url.pathname.split('/').filter(Boolean);
    const json = (body, status = 200) => route.fulfill({
      status, contentType: 'application/json', body: JSON.stringify(body),
    });

    if (url.pathname === '/api/auth/me') {
      return json({ actor_id: 'support-a', tenant_id: 'tenant-a', role: 'SUPPORT' });
    }
    if (url.pathname === '/api/sessions' && request.method() === 'GET') {
      return json({ items: sessions, limit: 50, offset: 0 });
    }
    if (url.pathname === '/api/s3/order-resources') return json({ items: [] });
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts.length === 3 && parts[2].endsWith('c01-a')) {
      const sessionId = parts[2];
      return json({
        session_id: sessionId, created_at: '2026-11-10T00:00:00Z',
        updated_at: '2026-11-10T00:01:00Z', tasks: [], s1_demo_resource: null,
      });
    }
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts[3] === 'messages') {
      const sessionId = parts[2];
      const total = messageCounts[sessionId] ?? 0;
      const limit = Number(url.searchParams.get('limit') ?? '100');
      let start = 1;
      let end = total;
      if (url.searchParams.has('before_seq')) {
        end = Math.min(total, Number(url.searchParams.get('before_seq')) - 1);
        start = Math.max(1, end - limit + 1);
      } else if (url.searchParams.has('after_seq')) {
        start = Math.min(total + 1, Number(url.searchParams.get('after_seq')) + 1);
        end = Math.min(total, start + limit - 1);
      } else if (url.searchParams.get('latest') === 'true') {
        start = Math.max(1, total - limit + 1);
      } else {
        end = Math.min(total, limit);
      }
      const items = end >= start
        ? Array.from({ length: end - start + 1 }, (_, offset) => message(sessionId, start + offset))
        : [];
      return json({ items, has_more_before: start > 1, has_more_after: end < total });
    }
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts[3] === 'runs') return json({ items: [] });
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts[3] === 'assistant' && parts[4] === 'scopes') {
      return json({ items: [], selected_project: null });
    }
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts[3] === 'events' && parts[4] === 'history') {
      return json({ items: [], after: Number(url.searchParams.get('after') ?? '0') });
    }
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts[3] === 'events') {
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': fixture\n\n' });
    }
    return json({ code: 'NOT_FOUND' }, 404);
  });
}

async function waitForVite() {
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(baseURL);
      if (response.ok) return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
  }
  throw new Error('Vite did not become ready.');
}

try {
  await waitForVite();
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const key = 'opspilot.selected-session.tenant-a.support-a';
  await context.addInitScript(({ storageKey }) => {
    localStorage.setItem(storageKey, 'session-a-c01-a');
  }, { storageKey: key });

  const page = await context.newPage();
  await installApiMocks(page);
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.session-item.selected')).toContainText('session-a-c01-a');
  await expect(page.getByText('session-a-message-1200', { exact: true })).toBeVisible();
  await expect(page.getByText('session-a-message-1', { exact: true })).toHaveCount(0);

  await page.getByRole('button', { name: /加载更早消息/ }).click();
  await expect(page.getByText('session-a-message-201', { exact: true })).toBeVisible();
  await expect(page.getByText('session-a-message-200', { exact: true })).toHaveCount(0);

  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('.session-item.selected')).toContainText('session-a-c01-a');
  await expect(page.getByText('session-a-message-1200', { exact: true })).toBeVisible();

  await page.locator('.session-item').filter({ hasText: 'session-b-c01-a' }).click();
  await expect(page.locator('.session-item.selected')).toContainText('session-b-c01-a');
  await expect(page.getByText('SESSION_B_ONLY_MESSAGE', { exact: true })).toBeVisible();
  await expect(page.getByText('session-a-message-1200', { exact: true })).toHaveCount(0);
  if (await page.evaluate((storageKey) => localStorage.getItem(storageKey), key) !== 'session-b-c01-a') {
    throw new Error('Selecting a Session did not update its browser restore key.');
  }

  const state = await context.storageState();
  await context.close();
  const restoredContext = await browser.newContext({
    viewport: { width: 1280, height: 900 }, storageState: state,
  });
  const restoredPage = await restoredContext.newPage();
  await installApiMocks(restoredPage);
  await restoredPage.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await expect(restoredPage.locator('.session-item.selected')).toContainText('session-b-c01-a');
  await expect(restoredPage.getByText('SESSION_B_ONLY_MESSAGE', { exact: true })).toBeVisible();
  await expect(restoredPage.getByText('session-a-message-1200', { exact: true })).toHaveCount(0);
  console.log(JSON.stringify({ status: 'PASS', selected_session_restore: true, latest_page_visible: true,
    older_page_loaded: true, refreshed: true, reopened_context: true, multi_session_isolated: true }));
  await restoredContext.close();
} finally {
  if (browser) await browser.close();
  vite.kill();
}
