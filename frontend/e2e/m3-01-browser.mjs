import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium, expect } from '@playwright/test';

const baseURL = process.env.OPSPILOT_UI_BASE_URL;
const supportPassword = process.env.OPSPILOT_E2E_SUPPORT_PASSWORD;
const approverPassword = process.env.OPSPILOT_E2E_APPROVER_PASSWORD;
const screenshotDir = process.env.OPSPILOT_EVIDENCE_SCREENSHOTS;
const sourceTaskId = process.env.OPSPILOT_M301_SOURCE_TASK_ID;

if (!baseURL || !supportPassword || !approverPassword || !screenshotDir || !sourceTaskId) {
  throw new Error('M3-01 browser evidence configuration is incomplete.');
}

await mkdir(screenshotDir, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1500, height: 1100 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const apiEvents = [];
const consoleErrors = [];
page.on('response', (response) => {
  const url = new URL(response.url());
  if (url.pathname.startsWith('/api/')) {
    apiEvents.push({ method: response.request().method(), path: url.pathname, status: response.status() });
  }
});
page.on('console', (message) => {
  if (message.type() === 'error') consoleErrors.push(message.text().slice(0, 240));
});

async function login(actorId, password) {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('演示身份').selectOption(actorId);
  await page.getByLabel('本地口令').fill(password);
  await page.getByRole('button', { name: '登录工作台' }).click();
  const ready = actorId.startsWith('approver-') ? '[data-testid="memory-approval-center"]' : '.rail-footer';
  await expect(page.locator(ready)).toBeVisible({ timeout: 20000 });
}

async function logout() {
  await page.getByRole('button', { name: '退出' }).click();
  await expect(page.getByRole('heading', { name: '登录 OpsPilot' })).toBeVisible();
}

async function findSessionWithTask(taskId) {
  return page.evaluate(async (wantedTaskId) => {
    const sessions = await fetch('/api/sessions').then((response) => response.json());
    for (const session of sessions.items) {
      const detail = await fetch(`/api/sessions/${encodeURIComponent(session.session_id)}`)
        .then((response) => response.json());
      if (detail.tasks.some((item) => item.task_id === wantedTaskId)) return session.session_id;
    }
    return null;
  }, taskId);
}

async function selectSession(sessionId, taskId) {
  const button = page.locator('.session-item').filter({ hasText: sessionId.slice(0, 22) }).first();
  await button.click();
  await expect(page.locator(`.task-summary-card[data-task-id="${taskId}"]`)).toBeVisible({ timeout: 20000 });
}

async function readJson(url) {
  const result = await page.evaluate(async (target) => {
    const response = await fetch(target);
    return { status: response.status, body: await response.json() };
  }, url);
  if (result.status !== 200) throw new Error(`GET ${url} returned ${result.status}.`);
  return result.body;
}

async function waitForTerminalRun(runId) {
  await expect.poll(async () => page.evaluate(async (targetRunId) => {
    const response = await fetch(`/api/runs/${encodeURIComponent(targetRunId)}`);
    return response.ok ? (await response.json()).status : `HTTP_${response.status}`;
  }, runId), { timeout: 240000, intervals: [500, 1000, 2000] }).toMatch(/WAITING_APPROVAL|WAITING_INPUT|SUCCEEDED|BLOCKED|FAILED/);
  return readJson(`/api/runs/${encodeURIComponent(runId)}`);
}

const result = {
  schema_version: 'm301-browser-v1',
  browser: 'Microsoft Edge via Playwright',
  base_url: baseURL,
  source_task_id: sourceTaskId,
  api_events: apiEvents,
  console_errors: consoleErrors,
};

try {
  await login('support-a', supportPassword);
  const sourceSessionId = await findSessionWithTask(sourceTaskId);
  if (!sourceSessionId) throw new Error('The real source Task A is not linked to a SUPPORT session.');
  await selectSession(sourceSessionId, sourceTaskId);
  const sourceOutcome = await readJson(`/api/tasks/${encodeURIComponent(sourceTaskId)}/outcome`);
  if (sourceOutcome.business_outcome !== 'DELIVERED') {
    throw new Error(`Source Task A outcome is ${sourceOutcome.business_outcome}, expected delivered S1 evidence.`);
  }
  await expect(page.getByTestId('create-memory-candidate')).toBeVisible({ timeout: 20000 });
  await page.screenshot({ path: path.join(screenshotDir, '01-source-task-a-ready.png'), fullPage: true });
  await page.getByTestId('create-memory-candidate').click();
  await expect(page.getByText(/真实来源候选已建立/)).toBeVisible({ timeout: 20000 });
  let sourceMemoryContext = await readJson(`/api/tasks/${encodeURIComponent(sourceTaskId)}/memories`);
  const candidate = sourceMemoryContext.source_memories.find((item) => item.state === 'CANDIDATE');
  if (!candidate) throw new Error('SUPPORT UI action did not create a persistent CANDIDATE.');
  result.source = {
    outcome: sourceOutcome.business_outcome, task_id: sourceTaskId,
    memory_id: candidate.memory_id, memory_version: candidate.version,
    memory_digest: candidate.content_digest, refs: candidate.source_refs,
  };
  await page.screenshot({ path: path.join(screenshotDir, '02-candidate-created.png'), fullPage: true });

  await logout();
  await login('approver-a', approverPassword);
  await page.getByTestId(`memory-candidate-${candidate.memory_id}`).click();
  await expect(page.getByTestId('memory-review-detail')).toContainText('CANDIDATE');
  await page.screenshot({ path: path.join(screenshotDir, '03-approver-review.png'), fullPage: true });
  page.once('dialog', (dialog) => { void dialog.accept(); });
  await page.getByTestId('confirm-memory').click();
  await expect(page.getByTestId('memory-review-detail')).toContainText('ACTIVE');
  const active = await readJson(`/api/memories/${encodeURIComponent(candidate.memory_id)}`);
  if (active.state !== 'ACTIVE' || active.confirmed_by !== 'approver-a') {
    throw new Error('Independent APPROVER confirmation was not persisted.');
  }
  result.approval = { state: active.state, version: active.version, confirmed_by: active.confirmed_by };
  await page.screenshot({ path: path.join(screenshotDir, '04-memory-confirmed.png'), fullPage: true });

  await logout();
  await login('support-a', supportPassword);
  await page.locator('.new-session-button').click();
  await expect(page.locator('.empty-conversation')).toBeVisible({ timeout: 15000 });
  await page.getByRole('button', { name: /新建调查任务/ }).click();
  await page.getByTestId('initial-symptom-input').fill('订单接口突然返回未认证，请调查当前绑定资源的原因，先不要改动配置。');
  const createPromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/tasks'));
  await page.getByRole('button', { name: /启动调查/ }).click();
  const createResponse = await createPromise;
  if (!createResponse.ok()) throw new Error(`Task B create returned ${createResponse.status()}.`);
  const target = await createResponse.json();
  if (target.task_id === sourceTaskId) throw new Error('Task B must be distinct from source Task A.');
  const targetRun = await waitForTerminalRun(target.run_id);
  let targetInspector = await readJson(`/api/tasks/${encodeURIComponent(target.task_id)}/inspector`);
  await expect.poll(async () => page.evaluate(async ({ taskId: wantedTaskId, memoryId }) => {
    const response = await fetch(`/api/tasks/${encodeURIComponent(wantedTaskId)}/inspector`);
    const inspector = await response.json();
    return inspector.investigator_context_provenance.some((item) =>
      item.selected_memories.some((memory) => memory.memory_id === memoryId));
  }, { taskId: target.task_id, memoryId: candidate.memory_id }), { timeout: 30000 }).toBe(true);
  targetInspector = await readJson(`/api/tasks/${encodeURIComponent(target.task_id)}/inspector`);
  const selectedContexts = targetInspector.investigator_context_provenance.flatMap((context) =>
    context.selected_memories.filter((memory) => memory.memory_id === candidate.memory_id)
      .map((memory) => ({
        call_id: context.call_id, prompt_digest: context.prompt_digest,
        model_status: context.model_status, selected_memory: memory,
      })));
  if (!selectedContexts.length || selectedContexts.some((item) => item.selected_memory.source_task_id !== sourceTaskId)) {
    throw new Error('Task B model ContextManifest does not show the approved cross-Task source.');
  }
  if (!targetInspector.investigation_model_traces.length || !targetInspector.observations.length) {
    throw new Error('Task B has no real Provider and MCP investigation traces.');
  }
  result.target = {
    task_id: target.task_id, run_id: target.run_id, run_status: targetRun.status,
    gate: targetInspector.current_gate,
    current_evidence: targetInspector.evidence.map((item) => ({
      evidence_id: item.evidence_id, fact_type: item.fact_type,
      versions: item.versions,
      facts: Object.fromEntries(Object.entries(item.facts ?? {}).filter(([key]) =>
        ['http_status', 'request_id', 'authn_result_code', 'outcome', 'reason_code',
          'missing_scopes', 'required_scopes', 'granted_scopes', 'principal_status'].includes(key))),
    })),
    selected_contexts: selectedContexts,
    model_traces: targetInspector.investigation_model_traces.map((item) => ({
      model_id: item.model_id, status: item.status, prompt_digest: item.prompt_digest,
      tool_names: item.tool_names, usage: item.usage,
    })),
    mcp_observations: targetInspector.observations.map((item) => ({
      tool_name: item.tool_name, status: item.status, evidence_id: item.evidence_id,
    })),
  };
  await page.screenshot({ path: path.join(screenshotDir, '05-task-b-memory-context.png'), fullPage: true });

  await logout();
  await login('approver-a', approverPassword);
  await page.getByTestId(`memory-candidate-${candidate.memory_id}`).click();
  await expect(page.getByTestId('memory-review-detail')).toContainText('ACTIVE');
  await page.screenshot({ path: path.join(screenshotDir, '06-approver-revoke-review.png'), fullPage: true });
  page.once('dialog', (dialog) => { void dialog.accept(); });
  await page.getByTestId('revoke-memory').click();
  await expect(page.getByTestId('memory-review-detail')).toContainText('REVOKED');
  const revoked = await readJson(`/api/memories/${encodeURIComponent(candidate.memory_id)}`);
  if (revoked.state !== 'REVOKED') throw new Error('Approver revocation did not persist.');
  result.revocation = { state: revoked.state, version: revoked.version, revoked_by: revoked.revoked_by };
  await page.screenshot({ path: path.join(screenshotDir, '07-memory-revoked.png'), fullPage: true });

  await logout();
  await login('support-a', supportPassword);
  const targetSession = await findSessionWithTask(target.task_id);
  if (!targetSession) throw new Error('Could not return to Task B after revocation.');
  await selectSession(targetSession, target.task_id);
  const assistantBefore = await page.locator('.message-row.assistant').count();
  await page.getByTestId('message-input').fill('结合当前的可信证据，下一步最适合核实什么？');
  await page.getByRole('button', { name: '发送消息' }).click();
  await expect.poll(() => page.locator('.message-row.assistant').count(), { timeout: 180000 }).toBe(assistantBefore + 1);
  const runs = await page.evaluate(async (sessionId) =>
    fetch(`/api/sessions/${encodeURIComponent(sessionId)}/runs`).then((response) => response.json()), targetSession);
  const chatRun = [...runs.items].reverse().find((item) => item.kind === 'CHAT_READONLY');
  if (!chatRun) throw new Error('No persistent CHAT_READONLY Run was created after revocation.');
  const chatContext = await readJson(`/api/runs/${encodeURIComponent(chatRun.run_id)}/context`);
  const manifest = chatContext.attempts?.at(-1)?.manifest;
  if (!manifest || manifest.memory_refs.length !== 0) {
    throw new Error('The post-revocation real chat model call loaded a stale Memory reference.');
  }
  sourceMemoryContext = await readJson(`/api/tasks/${encodeURIComponent(target.task_id)}/memories`);
  if (sourceMemoryContext.applicable_memories.some((item) => item.memory_id === candidate.memory_id)) {
    throw new Error('Revoked Memory remained applicable to Task B.');
  }
  result.after_revocation = {
    chat_run_id: chatRun.run_id, chat_run_status: chatRun.status,
    model_id: chatContext.attempts.at(-1).model_id,
    prompt_digest: manifest.prompt_digest,
    memory_refs: manifest.memory_refs,
    excluded_sources: manifest.excluded_sources,
    current_applicable_memory_ids: sourceMemoryContext.applicable_memories.map((item) => item.memory_id),
  };
  await page.screenshot({ path: path.join(screenshotDir, '08-after-revocation-no-memory.png'), fullPage: true });

  result.status = 'PASS';
  result.api_events = apiEvents;
  result.console_errors = consoleErrors;
  await writeFile(path.join(screenshotDir, 'BROWSER-TRACE.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify({ event: 'm301_browser', status: 'PASS', source_task_id: sourceTaskId,
    target_task_id: target.task_id, memory_id: candidate.memory_id,
    selected_context_count: selectedContexts.length, post_revoke_memory_refs: manifest.memory_refs.length,
    screenshot_count: 8, api_event_count: apiEvents.length, console_error_count: consoleErrors.length }));
} catch (error) {
  result.status = 'FAIL';
  result.error_class = error?.constructor?.name ?? 'Error';
  result.error = String(error?.message ?? error).slice(0, 500);
  result.api_events = apiEvents;
  result.console_errors = consoleErrors;
  await page.screenshot({ path: path.join(screenshotDir, 'FAILED.png'), fullPage: true }).catch(() => {});
  await writeFile(path.join(screenshotDir, 'BROWSER-TRACE.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  console.error(JSON.stringify({ event: 'm301_browser', status: 'FAIL', error_class: result.error_class,
    error: result.error, api_event_count: apiEvents.length }));
  process.exitCode = 1;
} finally {
  await browser.close();
}
