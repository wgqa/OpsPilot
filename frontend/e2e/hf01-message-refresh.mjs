import { spawn } from 'node:child_process';
import path from 'node:path';
import { chromium, expect } from '@playwright/test';

const baseURL = 'http://127.0.0.1:5191';
const s3Session = 'session-hf01-s3';
const otherSession = 'session-hf01-other';
const taskId = 'task-hf01-s3';
const answerText = 'HF01_RESTRICTED_OLD_ANSWER';
const staleNotice = 'HF01_SOURCE_INVALIDATED_NOTICE';
const vite = spawn(process.execPath, [
  path.resolve('node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5191', '--strictPort',
], { cwd: process.cwd(), windowsHide: true, stdio: 'ignore' });
let browser;
let staleSource = false;
let authorizationRevoked = false;
let eventHistoryReads = 0;
let latestPageRequests = 0;
let delayNextIncremental = true;
let delayNextStaleRevalidation = true;
let releaseIncremental;
let releaseRevalidation;
let incrementalStartedResolve;
let revalidationStartedResolve;
const incrementalStarted = new Promise((resolve) => { incrementalStartedResolve = resolve; });
const revalidationStarted = new Promise((resolve) => { revalidationStartedResolve = resolve; });

const sessions = [
  { session_id: s3Session, created_at: '2026-11-10T00:00:00Z', updated_at: '2026-11-10T00:01:00Z', task_count: 1 },
  { session_id: otherSession, created_at: '2026-11-10T00:00:00Z', updated_at: '2026-11-10T00:01:00Z', task_count: 0 },
];

function message(sessionId, sequence) {
  const isOther = sessionId === otherSession;
  const isOldAnswer = sessionId === s3Session && sequence === 202;
  return {
    message_id: `${sessionId}-message-${sequence}`,
    session_id: sessionId,
    task_id: isOldAnswer || (!isOther && sequence === 201) ? taskId : null,
    sequence,
    role: isOldAnswer ? 'ASSISTANT' : 'USER',
    input_kind: 'CHAT_READONLY',
    body: isOldAnswer ? (authorizationRevoked ? 'HF01_S3_AUTHORIZATION_HIDDEN' : staleSource ? staleNotice : answerText)
      : isOther ? 'HF01_OTHER_SESSION_ONLY' : `HF01_SESSION_A_${sequence}`,
    created_at: '2026-11-10T00:00:00Z',
    application_state: null,
    applied_run_id: null,
    investigation_origin_message_id: null,
    answer_run_id: isOldAnswer ? 'run-hf01-s3' : null,
    answer_source_message_id: isOldAnswer ? `${sessionId}-message-201` : null,
    answer_kind: isOldAnswer ? 'CHAT_MODEL' : null,
  };
}

function inspector() {
  return {
    task: { task_id: taskId, service_id: 'orders-async-demo', integration_id: 'integration-a', status: 'OPEN' },
    trusted_state: {
      task_status: 'OPEN',
      s3_outcome: authorizationRevoked
        ? { outcome: 'INCONCLUSIVE', currentness: 'INVALIDATED_BY_CURRENT_FACTS', recovered: false,
          gate: { decision: 'INCONCLUSIVE', reason_code: 'S3_AUTHORIZATION_UNAVAILABLE' } }
        : staleSource
          ? { outcome: 'INCONCLUSIVE', currentness: 'INVALIDATED_BY_CURRENT_FACTS', recovered: false,
            gate: { decision: 'INCONCLUSIVE', reason_code: 'S3_SLA_EXPIRED' } }
        : { outcome: 'INCONCLUSIVE', currentness: 'CURRENT', recovered: false,
          gate: { decision: 'INCONCLUSIVE', reason_code: 'NO_DIAGNOSIS' } },
    },
    plan_history: [], evidence: [], observations: [], runs: [], investigation_answers: [],
    readonly_followups: [], investigation_model_traces: [], chat_model_attempts: [],
    chat_context_provenance: [], task_input_messages: [], investigator_context_provenance: [],
    current_gate: { decision: 'INCONCLUSIVE', reason_code: authorizationRevoked ? 'S3_AUTHORIZATION_UNAVAILABLE'
      : staleSource ? 'S3_SLA_EXPIRED' : 'NO_DIAGNOSIS', checked_fact_ids: [] },
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

    if (url.pathname === '/api/auth/me') return json({ actor_id: 'support-a', tenant_id: 'tenant-a', role: 'SUPPORT' });
    if (url.pathname === '/api/sessions' && request.method() === 'GET') return json({ items: sessions, limit: 50, offset: 0 });
    if (url.pathname === '/api/s3/order-resources') return json({ items: [] });
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts.length === 3) {
      const sessionId = parts[2];
      return json({
        session_id: sessionId, created_at: '2026-11-10T00:00:00Z', updated_at: '2026-11-10T00:01:00Z',
        tasks: sessionId === s3Session ? [{ task_id: taskId, linked_at: '2026-11-10T00:00:00Z', is_primary: 1 }] : [],
        s1_demo_resource: null,
      });
    }
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts[3] === 'messages') {
      const sessionId = parts[2];
      if (sessionId === s3Session && url.searchParams.has('after_seq') && delayNextIncremental) {
        delayNextIncremental = false;
        incrementalStartedResolve();
        await new Promise((resolve) => { releaseIncremental = resolve; });
      }
      const total = sessionId === s3Session ? 1200 : 1;
      const limit = Number(url.searchParams.get('limit') ?? '500');
      let start = 1;
      let end = total;
      if (url.searchParams.has('before_seq')) {
        end = Math.min(total, Number(url.searchParams.get('before_seq')) - 1);
        start = Math.max(1, end - limit + 1);
      } else if (url.searchParams.has('after_seq')) {
        const after = Number(url.searchParams.get('after_seq'));
        start = Math.min(total + 1, after + 1);
        end = Math.min(total, start + limit - 1);
      } else if (url.searchParams.get('latest') === 'true') {
        if (sessionId === s3Session) latestPageRequests += 1;
        if (sessionId === s3Session && staleSource && delayNextStaleRevalidation) {
          delayNextStaleRevalidation = false;
          revalidationStartedResolve();
          await new Promise((resolve) => { releaseRevalidation = resolve; });
        }
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
      eventHistoryReads += 1;
      return json({ items: eventHistoryReads === 1 ? [] : [{
        event_seq: 76 + eventHistoryReads, event_kind: 'S3_DIAGNOSIS_FROZEN',
        happened_at: '2026-11-10T00:02:00Z', payload: { task_id: taskId },
      }], after: Number(url.searchParams.get('after') ?? '0') });
    }
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts[3] === 'events') {
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': hf01 fixture\n\n' });
    }
    if (parts[0] === 'api' && parts[1] === 'tasks' && parts[2] === taskId && parts[3] === 'inspector') return json(inspector());
    if (parts[0] === 'api' && parts[1] === 'tasks' && parts[2] === taskId && parts[3] === 'investigation-updates') return json({ items: [] });
    if (parts[0] === 'api' && parts[1] === 'tasks' && parts[2] === taskId && parts[3] === 's3-handoff') return json({});
    if (parts[0] === 'api' && parts[1] === 'tasks' && parts[2] === taskId && parts[3] === 'memories') {
      return json({ task_id: taskId, source_memories: [], applicable_memories: [], excluded_memories: [], context_provenance: [] });
    }
    if (parts[0] === 'api' && parts[1] === 'tasks' && parts[2] === taskId && parts[3] === 'semantic-memories') {
      return json({ task_id: taskId, project_id: null, source_candidates: [], active_project_memories: [], excluded: [] });
    }
    return json({ code: 'NOT_FOUND', path: url.pathname }, 404);
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
  const storageKey = 'opspilot.selected-session.tenant-a.support-a';
  await context.addInitScript(({ key, selected }) => localStorage.setItem(key, selected), { key: storageKey, selected: s3Session });
  const page = await context.newPage();
  await installApiMocks(page);
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.session-item.selected')).toContainText(s3Session);
  await page.getByRole('button', { name: /加载更早消息/ }).click();
  await expect(page.getByText(answerText, { exact: true })).toBeVisible();

  staleSource = true;
  await page.locator('.timeline-section .text-button').click();
  await incrementalStarted;
  await revalidationStarted;
  await expect(page.getByRole('button', { name: /加载更早消息/ })).toBeDisabled();
  if (releaseIncremental) releaseIncremental();
  releaseIncremental = null;

  // A second event arrives while the authoritative page walk is in flight.
  // It must be coalesced instead of invalidating that revalidation ticket.
  await page.locator('.timeline-section .text-button').click();
  await expect.poll(() => eventHistoryReads, { timeout: 3000 }).toBe(3);
  await new Promise((resolve) => setTimeout(resolve, 250));
  if (releaseRevalidation) releaseRevalidation();
  releaseRevalidation = null;
  await expect(page.getByText(staleNotice, { exact: true })).toBeVisible({ timeout: 3000 });
  await expect(page.getByText(answerText, { exact: true })).toHaveCount(0);

  authorizationRevoked = true;
  await page.locator('.timeline-section .text-button').click();
  await expect.poll(() => latestPageRequests, { timeout: 5000 }).toBe(4);
  await expect(page.getByText(staleNotice, { exact: true })).toHaveCount(0);
  await expect(page.getByText('HF01_S3_AUTHORIZATION_HIDDEN', { exact: true })).toHaveCount(0);
  await expect(page.locator('[data-message-id="session-hf01-s3-message-201"]')).toBeVisible();

  await page.locator('.session-item').filter({ hasText: otherSession }).click();
  await expect(page.locator('.session-item.selected')).toContainText(otherSession);
  await expect(page.getByText('HF01_OTHER_SESSION_ONLY', { exact: true })).toBeVisible();
  await expect(page.getByText(answerText, { exact: true })).toHaveCount(0);
  await page.locator('.session-item').filter({ hasText: s3Session }).click();
  await expect(page.locator('.session-item.selected')).toContainText(s3Session);
  await page.getByRole('button', { name: /加载更早消息/ }).click();
  await expect(page.locator('[data-message-id="session-hf01-s3-message-201"]')).toBeVisible();
  await expect(page.getByText(answerText, { exact: true })).toHaveCount(0);
  await expect(page.getByText(staleNotice, { exact: true })).toHaveCount(0);
  await expect(page.getByText('HF01_S3_AUTHORIZATION_HIDDEN', { exact: true })).toHaveCount(0);

  console.log(JSON.stringify({ status: 'PASS',
    historical_answer_initially_visible: true,
    source_invalidation_revalidated_loaded_older_page: true,
    incremental_refresh_had_no_new_messages: true,
    delayed_incremental_and_concurrent_refresh_fenced: true,
    s3_inspector_revocation_cleared_loaded_older_answer: true,
    switched_session_isolated: true,
    restored_revoked_session_sanitized: true,
  }));
  await context.close();
} finally {
  if (releaseIncremental) releaseIncremental();
  if (releaseRevalidation) releaseRevalidation();
  if (browser) await browser.close();
  vite.kill();
}
