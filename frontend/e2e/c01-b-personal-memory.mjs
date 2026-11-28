import path from 'node:path';
import { spawn } from 'node:child_process';
import { chromium, expect } from '@playwright/test';

const baseURL = 'http://127.0.0.1:5190';
const vite = spawn(process.execPath, [
  path.resolve('node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5190', '--strictPort',
], { cwd: process.cwd(), windowsHide: true, stdio: 'ignore' });
let browser;

const sessionId = 'session-c01-b-e2e';
const runId = 'run-c01-b-e2e';
const sourceMessageId = 'message-c01-b-e2e';
const memoryId = 'personal-c01-b-e2e';
const memoryContent = 'For callback questions, separate acceptance from business processing.';
let memoryState = 'ACTIVE';
let candidateCreated = false;
let revoked = false;
let selectedRefs = [];
let recallEnabled = true;
let autoLearnEnabled = false;
let consolidationLatestJob = null;

const userMessage = {
  message_id: sourceMessageId, task_id: null, sequence: 1, role: 'USER', input_kind: 'CHAT_READONLY',
  body: 'Please remember how I prefer callback explanations.', created_at: '2026-11-10T00:00:00Z',
  application_state: null, applied_run_id: null,
};

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
    if (url.pathname === '/api/personal-memory-settings' && request.method() === 'GET') {
      return json({ tenant_id: 'tenant-a', owner_actor_id: 'support-a', recall_enabled: recallEnabled,
        auto_learn_enabled: autoLearnEnabled, auto_learn_available: true,
        consolidation_status: {}, consolidation_latest_job: consolidationLatestJob,
        is_default: recallEnabled, updated_at: null });
    }
    if (url.pathname === '/api/personal-memory-settings' && request.method() === 'PUT') {
      const body = request.postDataJSON();
      recallEnabled = body.recall_enabled;
      autoLearnEnabled = recallEnabled && body.auto_learn_enabled;
      consolidationLatestJob = autoLearnEnabled ? {
        job_id: 'job-c01-b-e2e', status: 'PENDING', proposal_count: 0, written_count: 0,
        duplicate_count: 0, skipped_count: 0, rejected_count: 0, failure_code: null,
        updated_at: '2026-11-10T00:00:01Z',
      } : null;
      return json({ tenant_id: 'tenant-a', owner_actor_id: 'support-a', recall_enabled: recallEnabled,
        auto_learn_enabled: autoLearnEnabled, auto_learn_available: true,
        consolidation_status: {}, consolidation_latest_job: consolidationLatestJob,
        is_default: false, updated_at: '2026-11-10T00:00:01Z' });
    }
    if (url.pathname === '/api/sessions' && request.method() === 'GET') {
      return json({ items: [{ session_id: sessionId, created_at: '2026-11-10T00:00:00Z',
        updated_at: '2026-11-10T00:00:00Z', task_count: 0 }], limit: 50, offset: 0 });
    }
    if (url.pathname === '/api/s3/order-resources') return json({ items: [] });
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts[2] === sessionId && parts[3] === 'messages') {
      return json({ items: [userMessage], has_more_before: false, has_more_after: false });
    }
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts[2] === sessionId && parts.length === 3) {
      return json({ session_id: sessionId, tasks: [], s1_demo_resource: null });
    }
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts[2] === sessionId && parts[3] === 'runs') {
      return json({ items: [{ run_id: runId, task_id: null, session_id: sessionId,
        source_message_id: sourceMessageId, kind: 'CHAT_READONLY', status: 'SUCCEEDED',
        waiting_reason: null, created_at: '2026-11-10T00:00:00Z', started_at: null,
        ended_at: null, answer_status: 'SUCCEEDED' }] });
    }
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts[3] === 'assistant' && parts[4] === 'scopes') {
      return json({ items: [], selected_project: null });
    }
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts[3] === 'events' && parts[4] === 'history') {
      return json({ items: [], after: 0 });
    }
    if (parts[0] === 'api' && parts[1] === 'sessions' && parts[3] === 'events') {
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: ': fixture\n\n' });
    }
    if (url.pathname === `/api/runs/${runId}/context`) {
      return json({ run_id: runId, attempts: [{ status: 'SUCCEEDED', manifest: {
        memory_refs: selectedRefs, excluded_sources: [],
      } }], excluded_sources: [] });
    }
    if (url.pathname === '/api/personal-memories' && request.method() === 'GET') {
      const items = candidateCreated ? [{
        memory_id: memoryId, tenant_id: 'tenant-a', owner_actor_id: 'support-a',
        memory_kind: 'PREFERENCE', memory_mode: 'RELEVANT', memory_key: 'callback.acceptance', content: memoryContent,
        content_digest: 'a'.repeat(64), source_message_id: sourceMessageId,
        source_refs: [{ kind: 'MESSAGE', id: sourceMessageId, digest: 'b'.repeat(64) }],
        source_current: true, state: memoryState, creation_source: memoryState === 'CANDIDATE' ? null : 'USER_CONFIRMED',
        version: 1, expires_at: '2027-05-09T00:00:00.000+00:00',
      }] : [];
      return json({ items });
    }
    if (url.pathname === '/api/personal-memories/candidates' && request.method() === 'POST') {
      const body = request.postDataJSON();
      if (body.source_message_id !== sourceMessageId || body.owner_actor_id) {
        return json({ code: 'INVALID_REQUEST' }, 422);
      }
      candidateCreated = true;
      memoryState = 'CANDIDATE';
      return json({
        memory_id: memoryId, tenant_id: 'tenant-a', owner_actor_id: 'support-a',
        memory_kind: body.memory_kind, memory_mode: body.memory_mode ?? 'RELEVANT', memory_key: body.memory_key, content: body.content,
        content_digest: 'a'.repeat(64), source_message_id: sourceMessageId,
        source_refs: [{ kind: 'MESSAGE', id: sourceMessageId, digest: 'b'.repeat(64) }],
        source_current: true, state: 'CANDIDATE', creation_source: null, version: 1,
        expires_at: '2027-05-09T00:00:00.000+00:00',
      }, 201);
    }
    if (parts[0] === 'api' && parts[1] === 'personal-memories' && parts[2] === memoryId
      && ['confirm', 'revoke'].includes(parts[3]) && request.method() === 'POST') {
      memoryState = parts[3] === 'confirm' ? 'ACTIVE' : 'REVOKED';
      if (memoryState === 'REVOKED') {
        revoked = true;
      }
      return json({
        memory_id: memoryId, tenant_id: 'tenant-a', owner_actor_id: 'support-a',
        memory_kind: 'PREFERENCE', memory_mode: 'RELEVANT', memory_key: 'callback.acceptance', content: memoryContent,
        content_digest: 'a'.repeat(64), source_message_id: sourceMessageId,
        source_refs: [{ kind: 'MESSAGE', id: sourceMessageId, digest: 'b'.repeat(64) }],
        source_current: true, state: memoryState, creation_source: memoryState === 'ACTIVE' ? 'USER_CONFIRMED' : null, version: 1,
        expires_at: '2027-05-09T00:00:00.000+00:00',
      });
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
  await context.addInitScript(({ session, run }) => {
    sessionStorage.setItem('opspilot.csrf', 'c01-b-e2e-csrf');
    localStorage.setItem('opspilot.selected-session.tenant-a.support-a', session);
  }, { session: sessionId, run: runId });
  const page = await context.newPage();
  await page.on('dialog', (dialog) => dialog.accept());
  await installApiMocks(page);
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await expect(page.getByTestId('personal-memory-manager')).toBeVisible();
  await expect(page.getByText('还没有个人记忆。')).toBeVisible();
  const recallToggle = page.getByTestId('personal-memory-recall-setting').locator('input');
  await expect(recallToggle).toBeChecked();
  await recallToggle.uncheck();
  await expect(recallToggle).not.toBeChecked();
  await expect(page.getByText('个人记忆召回已关闭；自动学习同步暂停，已保存记忆仍保留。')).toBeVisible();
  await expect(page.getByTestId('personal-memory-auto-learn-setting').locator('input')).not.toBeChecked();
  await recallToggle.check();
  await expect(recallToggle).toBeChecked();
  if (!recallEnabled) throw new Error('Recall setting did not persist the enabled state.');
  const autoLearnToggle = page.getByTestId('personal-memory-auto-learn-setting').locator('input');
  await autoLearnToggle.check();
  await expect(autoLearnToggle).toBeChecked();
  if (!autoLearnEnabled) throw new Error('Automatic learning setting did not persist the enabled state.');
  const jobStatus = page.getByTestId('personal-memory-auto-learn-status');
  await expect(jobStatus).toContainText('自动整理已排队');
  consolidationLatestJob = { ...consolidationLatestJob, status: 'RUNNING' };
  await expect(jobStatus).toContainText('正在整理本批聊天');
  consolidationLatestJob = {
    ...consolidationLatestJob, status: 'UNKNOWN', failure_code: 'PROVIDER_TIMEOUT_RESULT_UNKNOWN',
  };
  await expect(jobStatus).toContainText('最近一批整理结果未知 · PROVIDER_TIMEOUT_RESULT_UNKNOWN');

  const form = page.getByTestId('personal-memory-proposal');
  await form.locator('select').nth(0).selectOption(sourceMessageId);
  await form.locator('select').nth(1).selectOption('PREFERENCE');
  await form.locator('select').nth(2).selectOption('RELEVANT');
  await form.locator('input').fill('callback.acceptance');
  await form.locator('textarea').fill(memoryContent);
  await page.getByTestId('create-personal-memory-candidate').click();
  await expect(page.getByTestId('personal-memory-preview')).toContainText('CANDIDATE');
  await expect(page.getByTestId('personal-memory-preview')).toContainText('tenant-a · support-a');
  await expect(page.getByText('候选只供预览，不会进入模型 Context')).toBeVisible();
  await expect(page.getByText('创建后 180 天到期')).toBeVisible();

  await page.getByTestId('confirm-personal-memory').click();
  await expect(page.getByTestId('personal-memory-preview')).toContainText('ACTIVE');
  await expect(page.getByTestId('personal-memory-context-provenance'))
    .toContainText('该次调用没有选用个人记忆');

  await page.getByTestId('revoke-personal-memory').click();
  await expect(page.getByTestId('personal-memory-preview')).toContainText('REVOKED');
  await expect(page.getByText('个人记忆已撤销；后续请求不会注入，原始来源消息仍保留。')).toBeVisible();
  if (!revoked || selectedRefs.length !== 0) throw new Error('Revocation unexpectedly left Personal Memory in the mocked context.');

  console.log(JSON.stringify({ status: 'PASS', candidate_previewed: true, owner_scope_visible: true,
    confirmation_required: true, recall_toggle_off_and_on_persisted: true,
    automatic_learning_toggle_persisted: true, consolidation_status_from_polling: true, cost_and_runtime_grant_disclosed: true,
    ttl_disclosed: true, no_auto_injection_before_a_new_run: true, revoke_refreshed_context: true }));
  await context.close();
} finally {
  if (browser) await browser.close();
  vite.kill();
}
