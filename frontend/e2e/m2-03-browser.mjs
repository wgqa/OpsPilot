import { execFileSync } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium, expect } from '@playwright/test';

const baseURL = process.env.OPSPILOT_UI_BASE_URL;
const supportPassword = process.env.OPSPILOT_E2E_SUPPORT_PASSWORD;
const screenshotDir = process.env.OPSPILOT_EVIDENCE_SCREENSHOTS;
const python = process.env.OPSPILOT_E2E_PYTHON;
const repoRoot = process.env.OPSPILOT_E2E_REPO_ROOT;
const dbPath = process.env.OPSPILOT_DB_PATH;
if (!baseURL || !supportPassword || !screenshotDir || !python || !repoRoot || !dbPath) {
  throw new Error('M2-03 browser smoke configuration is incomplete.');
}
await mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const secondPage = await context.newPage();
const network = [];
const handoffRequests = [];
const handoffResponses = [];
let routeCount = 0;
let releasePosts;
const bothPostsReached = new Promise((resolve) => { releasePosts = resolve; });
page.on('request', (request) => {
  const url = new URL(request.url());
  if (url.pathname.startsWith('/api/')) network.push({ type: 'request', method: request.method(), path: url.pathname });
});
page.on('response', (response) => {
  const url = new URL(response.url());
  if (url.pathname.startsWith('/api/')) network.push({ type: 'response', method: response.request().method(), path: url.pathname, status: response.status() });
});
page.on('console', (message) => {
  if (message.type() === 'error') network.push({ type: 'console_error', text: message.text().slice(0, 240) });
});
secondPage.on('request', (request) => {
  const url = new URL(request.url());
  if (url.pathname.startsWith('/api/')) network.push({ type: 'request', method: request.method(), path: url.pathname, page: 'second' });
});
secondPage.on('response', (response) => {
  const url = new URL(response.url());
  if (url.pathname.startsWith('/api/')) network.push({ type: 'response', method: response.request().method(), path: url.pathname, status: response.status(), page: 'second' });
});

function helper(...args) {
  const stdout = execFileSync(python, ['-X', 'utf8', '-m', 'opspilot.smokes.m2_02_hf_01', ...args], {
    cwd: repoRoot, encoding: 'utf8', timeout: 30000, windowsHide: true,
  });
  return JSON.parse(stdout.trim().split(/\r?\n/).at(-1));
}

async function taskInspector(targetPage, taskId) {
  const result = await targetPage.evaluate(async (id) => {
    const response = await fetch(`/api/tasks/${encodeURIComponent(id)}/inspector`);
    return { ok: response.ok, status: response.status, body: await response.json() };
  }, taskId);
  if (!result.ok) throw new Error(`Task inspector returned ${result.status}.`);
  return result.body;
}

async function startInvestigation(initialMessage) {
  await page.getByRole('button', { name: '新建调查任务' }).first().click();
  await page.getByTestId('initial-symptom-input').fill(initialMessage);
  const responsePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/tasks'));
  await page.getByRole('button', { name: '启动调查' }).click();
  const response = await responsePromise;
  if (!response.ok()) throw new Error(`Task create returned ${response.status()}.`);
  return response.json();
}

async function waitForRun(runId, timeout = 300000) {
  await expect.poll(async () => page.evaluate(async (id) => {
    const response = await fetch(`/api/runs/${encodeURIComponent(id)}`);
    if (!response.ok) return `HTTP_${response.status}`;
    return (await response.json()).status;
  }, runId), { timeout, intervals: [500, 1000, 2000] }).not.toMatch(/^(QUEUED|RUNNING|INTERRUPTED_RECOVERABLE)$/);
  return page.evaluate(async (id) => fetch(`/api/runs/${encodeURIComponent(id)}`).then((response) => response.json()), runId);
}

async function waitForCurrentDraft(taskId, runId, timeout = 300000) {
  await expect.poll(async () => {
    const inspector = await taskInspector(page, taskId);
    return inspector.s2_outcome?.business_outcome === 'HANDOFF_READY'
      && inspector.s2_outcome?.currentness === 'CURRENT'
      && inspector.s2_outcome?.diagnosis_receipt?.run_id === runId ? 'READY' : 'PENDING';
  }, { timeout, intervals: [250, 500, 1000] }).toBe('READY');
  return taskInspector(page, taskId);
}

async function login() {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('演示身份').selectOption('support-a');
  await page.getByLabel('本地口令').fill(supportPassword);
  await page.getByRole('button', { name: '登录工作台' }).click();
  await expect(page.locator('.rail-footer')).toBeVisible({ timeout: 15000 });
  const response = network.find((item) => item.type === 'response' && item.path === '/api/auth/login');
  if (!response || response.status !== 200) throw new Error('Browser login did not return HTTP 200.');
}

function hasUnnegatedRecoveryOrAuthorizationClaim(answer) {
  const clauses = answer.toLocaleLowerCase()
    .split(/[\n。！？!?；;，,]/)
    .map((clause) => clause.replace(/\s+/g, ''));
  const claims = [
    /(?:scopeis(?:authorized|granted)|scopehasbeen(?:authorized|granted)|范围.{0,20}(?:已授权|已授予|已开通)|权限.{0,20}(?:已授权|已授予|已开通))/g,
    /(?:订单查询业务|订单api|api|业务).{0,20}(?:已恢复|已经恢复|恢复正常|recovered|restored)/g,
  ];
  const negations = [
    '没有证据', '不代表', '不表示', '尚未', '仍未', '并未', '没有', '未', '不能', '无法',
    'notyet', 'hasnot', 'havenot', 'noevidence', 'notauthorized', 'notrecovered', 'cannot', 'unableto',
  ];
  return clauses.some((clause) => claims.some((pattern) => {
    pattern.lastIndex = 0;
    return [...clause.matchAll(pattern)].some((match) => {
      const prefix = clause.slice(Math.max(0, (match.index ?? 0) - 48), match.index ?? 0);
      return !negations.some((negation) => prefix.includes(negation));
    });
  }));
}

try {
  await login();
  await page.locator('.new-session-button').click();
  const created = await startInvestigation('订单查询 API 的调用方收到了权限错误，我不确定具体状态码；请核实当前绑定服务的真实情况。');
  const taskId = String(created.task_id);
  const initialRunId = String(created.run_id);
  const initialRun = await waitForRun(initialRunId);
  const initialInspector = await taskInspector(page, taskId);
  const initialOutcome = initialInspector.s2_outcome;
  const initialReceipt = initialOutcome?.diagnosis_receipt;
  if (!initialReceipt?.request_id || !['HANDOFF_READY', 'DIAGNOSED'].includes(initialOutcome?.business_outcome)) {
    throw new Error(`Initial live investigation did not persist a correlated S2 diagnosis: ${initialRun.status}.`);
  }
  const sessions = await page.evaluate(async () => fetch('/api/sessions').then((response) => response.json()));
  const sessionId = String(sessions.items[0]?.session_id ?? '');
  if (!sessionId) throw new Error('Persisted Task session is missing.');
  await page.screenshot({ path: path.join(screenshotDir, '01-real-diagnosis.png'), fullPage: true });

  const correctedRequest = helper('--probe-only', '--db', dbPath, '--task-id', taskId);
  if (correctedRequest.status !== 403 || !correctedRequest.request_id
      || correctedRequest.request_id === initialReceipt.request_id || !correctedRequest.binding_matches) {
    throw new Error('The corrective clue was not a distinct, same-TaskBinding live HTTP 403.');
  }
  const correctionText = `正式关键纠错：上一轮 Request ID ${initialReceipt.request_id} 已不是当前请求。`
    + `请基于这个新的真实请求 ${correctedRequest.request_id} 重新调查。`
    + '它只是线索；继续使用当前 Task 绑定的订单服务、集成、主体和路由，不要改变绑定或授予权限。';
  let correctionWarning = '';
  page.once('dialog', async (dialog) => { correctionWarning = dialog.message(); await dialog.accept(); });
  const correctionResponsePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/messages'));
  await page.getByTestId('critical-correction-input').fill(correctionText);
  await page.getByTestId('submit-critical-correction').click();
  const correctionResponse = await correctionResponsePromise;
  if (correctionResponse.status() !== 202) throw new Error(`Formal correction returned ${correctionResponse.status()}, expected 202.`);
  const correction = await correctionResponse.json();
  if (correction.input_kind !== 'CORRECT_TASK_INPUT' || !correctionWarning.includes('中断当前业务调查')) {
    throw new Error('The browser did not submit the formal correction with its TaskControl warning.');
  }
  const correctedRunId = String(correction.run_id);
  const correctedRun = await waitForRun(correctedRunId);
  const correctedInspector = await waitForCurrentDraft(taskId, correctedRunId);
  const correctedOutcome = correctedInspector.s2_outcome;
  const correctedReceipt = correctedOutcome.diagnosis_receipt;
  const correctedDraft = correctedOutcome.draft;
  const appliedCorrection = correctedInspector.task_input_messages.find((item) => item.message_id === correction.message_id);
  const correctedContext = correctedInspector.investigator_context_provenance.find((item) =>
    item.task_run_control?.run_id === correctedRunId);
  if (!correctedReceipt || !correctedDraft || correctedReceipt.request_id === initialReceipt.request_id
      || correctedReceipt.request_id === correctedRequest.request_id
      || appliedCorrection?.application_state !== 'APPLIED_TO_RUN'
      || appliedCorrection?.applied_run_id !== correctedRunId
      || !correctedContext?.selected_input_messages?.some((item) => item.message_id === correction.message_id)
      || correctedOutcome.submitted !== false || correctedOutcome.scope_authorized !== false) {
    throw new Error('Corrected Run did not create a new current unsubmitted receipt and frozen Draft.');
  }
  await expect(page.getByTestId('submit-s2-handoff')).toBeVisible();
  await page.screenshot({ path: path.join(screenshotDir, '02-correction-and-current-draft.png'), fullPage: true });

  // A second real tab shares this browser's cookies and localStorage. Seed only the
  // per-tab CSRF token so both pages act as the same trusted SUPPORT owner.
  const csrf = await page.evaluate(() => globalThis.sessionStorage.getItem('opspilot.csrf'));
  if (!csrf) throw new Error('The authenticated tab has no CSRF token.');
  await secondPage.addInitScript((token) => globalThis.sessionStorage.setItem('opspilot.csrf', token), csrf);
  await secondPage.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await expect(secondPage.locator('.rail-footer')).toBeVisible({ timeout: 15000 });
  await expect(secondPage.getByTestId('submit-s2-handoff')).toBeVisible({ timeout: 15000 });

  // Hold both POSTs until both tabs have completed their preflight GET. The first
  // real POST is allowed to commit but its response is deliberately dropped;
  // the other tab replays the same stable operation and receives the same receipt.
  await context.route('**/api/tasks/*/handoff/submit', async (route) => {
    const request = route.request();
    const body = request.postDataJSON();
    handoffRequests.push({
      method: request.method(), operation_id: body.operation_id,
      draft_id: body.draft_id, draft_digest: body.draft_digest,
      expected_control_revision: body.expected_control_revision,
      idempotency_key: request.headers()['idempotency-key'],
      page: request.frame().page() === secondPage ? 'second' : 'first',
    });
    routeCount += 1;
    if (routeCount >= 2) releasePosts();
    await bothPostsReached;
    const response = await route.fetch();
    const responseBody = await response.json();
    handoffResponses.push({ status: response.status(), body: responseBody });
    if (request.frame().page() === page) {
      await route.abort('failed');
      return;
    }
    await route.fulfill({ response, body: JSON.stringify(responseBody) });
  });
  let dialogCount = 0;
  page.on('dialog', async (dialog) => { dialogCount += 1; await dialog.accept(); });
  secondPage.on('dialog', async (dialog) => { dialogCount += 1; await dialog.accept(); });
  const beforeSubmit = helper('--snapshot-only', '--db', dbPath, '--task-id', taskId);
  await Promise.all([
    page.getByTestId('submit-s2-handoff').click(),
    secondPage.getByTestId('submit-s2-handoff').click(),
  ]);
  await expect(page.getByTestId('handoff-receipt')).toBeVisible({ timeout: 30000 });
  await expect(secondPage.getByTestId('handoff-receipt')).toBeVisible({ timeout: 30000 });
  const firstReceiptId = await page.getByTestId('handoff-receipt').locator('code').innerText();
  const secondReceiptId = await secondPage.getByTestId('handoff-receipt').locator('code').innerText();
  if (firstReceiptId !== secondReceiptId || handoffRequests.length !== 2
      || handoffRequests[0].operation_id !== handoffRequests[1].operation_id
      || handoffRequests.some((item) => item.operation_id !== item.idempotency_key)
      || handoffResponses.length !== 2 || !handoffResponses.some((item) => item.status === 202)
      || !handoffResponses.some((item) => item.status === 200)) {
    throw new Error('Two-tab submit did not reuse one operation ID and recover the committed receipt after a lost response.');
  }
  await expect(page.getByTestId('task-outcome')).toContainText('SCOPE_ESCALATED');
  await expect(page.getByTestId('handoff-accepted')).toContainText('未授予 Scope');
  const afterSubmit = helper('--snapshot-only', '--db', dbPath, '--task-id', taskId);
  const finalHandoff = await page.evaluate(async (id) =>
    fetch(`/api/tasks/${encodeURIComponent(id)}/handoff`).then((response) => response.json()), taskId);
  if (finalHandoff.business_outcome !== 'SCOPE_ESCALATED'
      || finalHandoff.handoff_receipt?.receipt_id !== firstReceiptId
      || !finalHandoff.handoff_receipt?.queue_entry_id) {
    throw new Error('The read API did not return the persisted receipt and queue identity.');
  }
  const submitUnchanged = beforeSubmit.protected_table_counts.s2_gate_traces
      === afterSubmit.protected_table_counts.s2_gate_traces
    && beforeSubmit.protected_table_counts.s2_diagnosis_receipts
      === afterSubmit.protected_table_counts.s2_diagnosis_receipts
    && afterSubmit.s2_projection.business_outcome === 'SCOPE_ESCALATED'
    && afterSubmit.s2_projection.submitted === true
    && afterSubmit.s2_projection.scope_authorized === false;
  if (!submitUnchanged) throw new Error('Handoff altered diagnostic evidence or authorized Scope.');
  const operationStorageKey = `opspilot.m2-03.handoff.${taskId}.${correctedDraft.draft_id}`;
  const operationIdBeforeReload = await page.evaluate((key) => {
    const raw = globalThis.localStorage.getItem(key);
    return raw ? JSON.parse(raw).operation_id : null;
  }, operationStorageKey);
  if (operationIdBeforeReload !== handoffRequests[0].operation_id) {
    throw new Error('The browser did not persist the submitted operation ID in localStorage.');
  }
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('.rail-footer')).toBeVisible({ timeout: 15000 });
  await expect(page.getByTestId('handoff-receipt')).toBeVisible({ timeout: 30000 });
  const reloadedReceiptId = await page.getByTestId('handoff-receipt').locator('code').innerText();
  const operationIdAfterReload = await page.evaluate((key) => {
    const raw = globalThis.localStorage.getItem(key);
    return raw ? JSON.parse(raw).operation_id : null;
  }, operationStorageKey);
  if (reloadedReceiptId !== firstReceiptId || operationIdAfterReload !== operationIdBeforeReload) {
    throw new Error('Reload did not preserve the stable operation ID and reconciled HandoffReceipt.');
  }
  await page.screenshot({ path: path.join(screenshotDir, '03-accepted-receipt.png'), fullPage: true });

  const beforeChat = helper('--snapshot-only', '--db', dbPath, '--task-id', taskId);
  const priorAssistantCount = await page.locator('.message-row.assistant').count();
  await page.getByTestId('message-input').fill('现在这份申请到哪一步了？业务恢复了吗？');
  const messageResponsePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/messages'));
  await page.getByRole('button', { name: '发送消息' }).click();
  const messageResponse = await messageResponsePromise;
  if (!messageResponse.ok()) throw new Error(`Post-handoff read-only chat returned ${messageResponse.status()}.`);
  const acceptedMessage = await messageResponse.json();
  await expect.poll(async () => page.locator('.message-row.assistant').count(),
    { timeout: 180000, intervals: [250, 500, 1000] }).toBe(priorAssistantCount + 1);
  const answer = await page.locator('.message-row.assistant').last().innerText();
  await expect.poll(async () => page.evaluate(async (id) => {
    const runs = await fetch(`/api/sessions/${encodeURIComponent(id)}/runs`).then((response) => response.json());
    return [...runs.items].reverse().find((item) => item.kind === 'CHAT_READONLY')?.status ?? 'MISSING';
  }, sessionId), { timeout: 180000, intervals: [250, 500, 1000] }).toBe('SUCCEEDED');
  const afterChat = helper('--snapshot-only', '--db', dbPath, '--task-id', taskId);
  if (JSON.stringify(beforeChat) !== JSON.stringify(afterChat)) {
    throw new Error('Read-only result follow-up changed Task, Queue, Receipt, Ledger, or authorization facts.');
  }
  const deniesAuthorization = /未授权|没有.{0,5}(?:获得|得到)?授权|授权.{0,8}(?:未发生|未变更|没有)|not.{0,8}authorized|scope_authorized.{0,10}false/i.test(answer);
  const deniesRecovery = /尚未.{0,5}恢复|未.{0,5}恢复|没有.{0,12}恢复|不能.{0,12}(?:宣称|确认|说).{0,12}恢复|no.{0,10}(?:recovery|evidence).{0,20}(?:recover|restore)|not.{0,10}(?:recovered|restored)/i.test(answer);
  if (!/本地队列|人工处理|受理|接收/.test(answer) || !deniesAuthorization || !deniesRecovery) {
    throw new Error(`Post-handoff answer did not explain receipt and non-recovery accurately: ${answer.slice(0, 500)}`);
  }
  if (hasUnnegatedRecoveryOrAuthorizationClaim(answer)) {
    throw new Error(`Post-handoff answer made an unsupported authorization or recovery claim: ${answer.slice(0, 500)}`);
  }
  await page.screenshot({ path: path.join(screenshotDir, '04-readonly-result-followup.png'), fullPage: true });

  const result = {
    status: 'PASS', browser: 'Microsoft Edge', task_id: taskId, session_id: sessionId,
    initial_run: { run_id: initialRunId, status: initialRun.status,
      business_outcome: initialOutcome.business_outcome, receipt_id: initialReceipt.receipt_id,
      request_id: initialReceipt.request_id },
    correction: { message_id: correction.message_id, run_id: correctedRunId,
      status: correctedRun.status, control_revision: correction.expected_control_revision,
      external_request_id: correctedRequest.request_id,
      receipt_id: correctedReceipt.receipt_id, request_id: correctedReceipt.request_id,
      draft_id: correctedDraft.draft_id, draft_digest: correctedDraft.content_digest },
    handoff: { two_tabs: true, dialog_count: dialogCount, requests: handoffRequests,
      received_responses: handoffResponses, response_lost_on_first_tab: true,
      receipt_id: firstReceiptId, queue_entry_id: finalHandoff.handoff_receipt.queue_entry_id,
      operation_id: handoffRequests[0].operation_id,
      operation_id_persisted_across_reload: operationIdAfterReload === operationIdBeforeReload,
      receipt_reconciled_after_reload: reloadedReceiptId === firstReceiptId,
      business_outcome: afterSubmit.s2_projection.business_outcome,
      submitted: afterSubmit.s2_projection.submitted,
      scope_authorized: afterSubmit.s2_projection.scope_authorized,
      recovery_claimed: false },
    followup: { message_id: acceptedMessage.message_id, answer, business_state_unchanged: true },
    request_id_chain: [initialReceipt.request_id, correctedRequest.request_id, correctedReceipt.request_id],
    protected_snapshot_before_submit: beforeSubmit,
    protected_snapshot_after_submit: afterSubmit,
    protected_snapshot_before_followup: beforeChat,
    protected_snapshot_after_followup: afterChat,
    network,
  };
  await writeFile(path.join(screenshotDir, 'browser-trace.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify(result));
} finally {
  await context.close();
  await browser.close();
}
