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
  throw new Error('HF-01 browser smoke configuration is incomplete.');
}
await mkdir(screenshotDir, { recursive: true });

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const network = [];
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

function helper(...args) {
  const stdout = execFileSync(python, ['-X', 'utf8', '-m', 'opspilot.smokes.m2_02_hf_01', ...args], {
    cwd: repoRoot,
    encoding: 'utf8',
    timeout: 30000,
    windowsHide: true,
  });
  return JSON.parse(stdout.trim().split(/\r?\n/).at(-1));
}

function hasPositiveReadonlyCompletionClaim(answer) {
  const claims = [
    '已经修好', '已修好', '已经修复', '已修复', '已经恢复', '已恢复', '已经提交', '已提交工单',
    '已经交接', '已交接', 'already fixed', 'has been fixed', 'already repaired', 'has been repaired',
    'already recovered', 'has recovered', 'already submitted', 'has been submitted',
    'already handed off', 'has been handed off',
  ];
  const negations = [
    '不能说', '不能确认', '不能认定', '无法确认', '无法认定', '尚未', '还未', '没有', '并未', '未曾',
    '没有证据', '用户说', '用户称', 'not yet', 'has not', "hasn't", 'have not', "haven't",
    'cannot say', "can't say", 'cannot determine', 'cannot conclude', 'no evidence',
    'user says', 'user claims',
  ];
  const clauses = answer.toLocaleLowerCase().split(/[\n。！？!?；;，,]/);
  return clauses.some((clause) => claims.some((claim) => {
    const normalizedClaim = claim.toLocaleLowerCase();
    for (const match of clause.matchAll(new RegExp(normalizedClaim.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'))) {
      const prefix = clause.slice(Math.max(0, match.index - 36), match.index);
      if (!negations.some((marker) => prefix.includes(marker.toLocaleLowerCase()))) return true;
    }
    return false;
  }));
}

async function taskInspector(taskId) {
  const response = await page.evaluate(async (id) => {
    const result = await fetch(`/api/tasks/${encodeURIComponent(id)}/inspector`);
    return { ok: result.ok, status: result.status, body: await result.json() };
  }, taskId);
  if (!response.ok) throw new Error(`Task inspector returned ${response.status}.`);
  return response.body;
}

async function startInvestigation(initialMessage) {
  await page.getByRole('button', { name: '新建调查任务' }).first().click();
  await page.getByTestId('initial-symptom-input').fill(initialMessage);
  const responsePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/tasks'));
  await page.getByRole('button', { name: '启动调查' }).click();
  const response = await responsePromise;
  if (!response.ok()) throw new Error(`Task create returned ${response.status()}.`);
  const created = await response.json();
  await expect.poll(async () => page.locator('.task-summary-card').getAttribute('data-task-id'),
    { timeout: 30000, intervals: [100, 250, 500] }).toBe(created.task_id);
  return created;
}

async function waitForRun(runId, timeout = 240000) {
  await expect.poll(async () => page.evaluate(async (id) => {
    const response = await fetch(`/api/runs/${encodeURIComponent(id)}`);
    if (!response.ok) return `HTTP_${response.status}`;
    return (await response.json()).status;
  }, runId), { timeout, intervals: [500, 1000, 2000] }).not.toMatch(/^(QUEUED|RUNNING|INTERRUPTED_RECOVERABLE)$/);
  return page.evaluate(async (id) => fetch(`/api/runs/${encodeURIComponent(id)}`).then((response) => response.json()), runId);
}

async function waitForOutcome(taskId, predicate, timeout = 30000) {
  await expect.poll(async () => {
    const inspector = await taskInspector(taskId);
    return predicate(inspector) ? 'READY' : 'PENDING';
  }, { timeout, intervals: [250, 500, 1000] }).toBe('READY');
  return taskInspector(taskId);
}

async function login() {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('演示身份').selectOption('support-a');
  await page.getByLabel('本地口令').fill(supportPassword);
  await page.getByRole('button', { name: '登录工作台' }).click();
  await expect(page.locator('.rail-footer')).toBeVisible({ timeout: 15000 });
  const loginResponse = network.find((item) => item.type === 'response' && item.path === '/api/auth/login');
  if (!loginResponse || loginResponse.status !== 200) throw new Error('Browser login did not return HTTP 200.');
}

async function sendReadOnlyQuestion(body) {
  const priorCount = await page.locator('.message-row.assistant').count();
  await page.getByTestId('message-input').fill(body);
  const responsePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/messages'));
  await page.getByRole('button', { name: '发送消息' }).click();
  const response = await responsePromise;
  if (!response.ok()) throw new Error(`CHAT_READONLY message returned ${response.status()}.`);
  const accepted = await response.json();
  await expect.poll(async () => page.locator('.message-row.assistant').count(),
    { timeout: 120000, intervals: [250, 500, 1000] }).toBe(priorCount + 1);
  const sessions = await page.evaluate(async () => fetch('/api/sessions').then((result) => result.json()));
  const sessionId = String(sessions.items[0]?.session_id ?? '');
  if (!sessionId) throw new Error('CHAT_READONLY session is missing after message acceptance.');
  await expect.poll(async () => page.evaluate(async (id) => {
    const runs = await fetch(`/api/sessions/${encodeURIComponent(id)}/runs`).then((result) => result.json());
    return [...runs.items].reverse().find((item) => item.kind === 'CHAT_READONLY')?.status ?? 'MISSING';
  }, sessionId), { timeout: 120000, intervals: [250, 500, 1000] }).toBe('SUCCEEDED');
  await expect.poll(async () => page.locator('.message-row.assistant').last().innerText(),
    { timeout: 10000, intervals: [250, 500] }).not.toBe('');
  return {
    accepted,
    session_id: sessionId,
    answer: await page.locator('.message-row.assistant').last().innerText(),
  };
}

try {
  await login();
  await page.locator('.new-session-button').click();
  const created = await startInvestigation('订单接口最近不能正常使用，我不确定具体状态码；请核实当前绑定服务的真实情况。');
  const taskId = String(created.task_id);
  const initialRunId = String(created.run_id);
  const initialRun = await waitForRun(initialRunId);
  const initialInspector = await waitForOutcome(taskId, (item) =>
    ['HANDOFF_READY', 'DIAGNOSED'].includes(item.s2_outcome?.business_outcome));
  const initialOutcome = initialInspector.s2_outcome;
  const initialReceipt = initialOutcome?.diagnosis_receipt;
  if (!initialReceipt || !initialReceipt.request_id) {
    throw new Error(`Initial Web investigation did not persist a correlated diagnosis: ${initialRun.status}.`);
  }
  const sessionList = await page.evaluate(async () => fetch('/api/sessions').then((response) => response.json()));
  const sessionId = String(sessionList.items[0]?.session_id ?? '');
  if (!sessionId) throw new Error('Task browser session was not persisted.');
  await page.screenshot({ path: path.join(screenshotDir, '01-initial-diagnosis.png'), fullPage: true });

  const correctedRequest = helper('--probe-only', '--db', dbPath, '--task-id', taskId);
  if (correctedRequest.status !== 403 || !correctedRequest.request_id
      || correctedRequest.request_id === initialReceipt.request_id || !correctedRequest.binding_matches) {
    throw new Error('The second live request was not a distinct, same-TaskBinding HTTP 403.');
  }
  const correctionText = (
    `正式关键纠错：上一轮的 Request ID ${initialReceipt.request_id} 已不是当前请求。`
    + `请基于这个新的真实请求 ${correctedRequest.request_id} 重新调查。`
    + '它只是线索；继续使用当前 Task 绑定的订单服务、集成、主体和路由，不要改变绑定或授予权限。'
  );
  let warning = '';
  page.once('dialog', async (dialog) => { warning = dialog.message(); await dialog.accept(); });
  const correctionResponsePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/messages'));
  await page.getByTestId('critical-correction-input').fill(correctionText);
  await page.getByTestId('submit-critical-correction').click();
  const correctionResponse = await correctionResponsePromise;
  if (correctionResponse.status() !== 202) throw new Error(`Critical correction returned ${correctionResponse.status()}, expected 202.`);
  const correction = await correctionResponse.json();
  if (correction.input_kind !== 'CORRECT_TASK_INPUT' || !warning.includes('中断当前业务调查')) {
    throw new Error('The browser did not submit a formal critical correction with its control warning.');
  }
  const correctedRunId = String(correction.run_id);
  const correctedRun = await waitForRun(correctedRunId);
  const correctedInspector = await waitForOutcome(taskId, (item) =>
    item.s2_outcome?.business_outcome === 'HANDOFF_READY'
      && item.s2_outcome?.currentness === 'CURRENT'
      && item.s2_outcome?.diagnosis_receipt?.run_id === correctedRunId,
  240000);
  const correctedOutcome = correctedInspector.s2_outcome;
  const correctedReceipt = correctedOutcome.diagnosis_receipt;
  const correctedDraft = correctedOutcome.draft;
  const appliedCorrection = correctedInspector.task_input_messages.find((item) => item.message_id === correction.message_id);
  const correctedContext = correctedInspector.investigator_context_provenance.find((item) =>
    item.task_run_control?.run_id === correctedRunId);
  if (!correctedReceipt || !correctedDraft || correctedReceipt.request_id === initialReceipt.request_id
      || correctedReceipt.request_id === correctedRequest.request_id
      || correctedDraft.receipt_id !== correctedReceipt.receipt_id
      || appliedCorrection?.application_state !== 'APPLIED_TO_RUN'
      || appliedCorrection?.applied_run_id !== correctedRunId
      || !correctedContext?.selected_input_messages?.some((item) => item.message_id === correction.message_id)
      || correctedOutcome.submitted !== false || correctedOutcome.scope_authorized !== false) {
    throw new Error('Corrected Run did not create a fresh, unsubmitted, current DiagnosisReceipt and Draft.');
  }
  await page.screenshot({ path: path.join(screenshotDir, '02-formal-correction.png'), fullPage: true });
  await page.screenshot({ path: path.join(screenshotDir, '03-corrected-diagnosis-draft.png'), fullPage: true });

  const beforeChat = helper('--snapshot-only', '--db', dbPath, '--task-id', taskId);
  const chat = await sendReadOnlyQuestion('现在修好了吗？申请提交了吗？');
  const afterChat = helper('--snapshot-only', '--db', dbPath, '--task-id', taskId);
  const unchanged = JSON.stringify(beforeChat) === JSON.stringify(afterChat);
  if (!unchanged) throw new Error('CHAT_READONLY changed the S2 business Task or its protected side-effect counters.');
  const answerClauses = chat.answer.toLocaleLowerCase().split(/[\n。！？!?；;，,]/);
  const answerConfirmsNoRepair = answerClauses.some((clause) =>
    /修好|修复|恢复|fixed|repaired|recovered/i.test(clause)
      && /没有|无|未|尚未|还未|不能|无法|不曾|not yet|has not|no evidence|cannot|can't/i.test(clause));
  const answerConfirmsNoSubmission = answerClauses.some((clause) =>
    /提交|交接|submitted|handed off/i.test(clause)
      && /没有|无|未|尚未|还未|不能|无法|不曾|not yet|has not|no evidence|cannot|can't/i.test(clause));
  if (!answerConfirmsNoRepair || !answerConfirmsNoSubmission || hasPositiveReadonlyCompletionClaim(chat.answer)) {
    throw new Error(`CHAT_READONLY answer did not faithfully explain HANDOFF_READY: ${chat.answer.slice(0, 500)}`);
  }
  await page.screenshot({ path: path.join(screenshotDir, '04-readonly-result-followup.png'), fullPage: true });
  const sessionRuns = await page.evaluate(async (id) =>
    fetch(`/api/sessions/${encodeURIComponent(id)}/runs`).then((response) => response.json()), sessionId);
  const chatRun = [...sessionRuns.items].reverse().find((item) => item.kind === 'CHAT_READONLY');
  if (!chatRun || chatRun.status !== 'SUCCEEDED') throw new Error('Final read-only question did not persist as a successful CHAT_READONLY Run.');

  const result = {
    status: 'PASS',
    browser: 'Microsoft Edge',
    task_id: taskId,
    session_id: sessionId,
    initial_message_id: created.message_id,
    initial_run: { run_id: initialRunId, status: initialRun.status, outcome: initialOutcome.business_outcome,
      receipt_id: initialReceipt.receipt_id, request_id: initialReceipt.request_id },
    correction: { message_id: correction.message_id, run_id: correctedRunId,
      status: correctedRun.status, control_revision: correction.expected_control_revision,
      applied_control: correctedContext.task_run_control,
      external_request_id: correctedRequest.request_id },
    corrected: { outcome: correctedOutcome.business_outcome, currentness: correctedOutcome.currentness,
      receipt_id: correctedReceipt.receipt_id, draft_id: correctedDraft.draft_id,
      run_id: correctedReceipt.run_id, request_id: correctedReceipt.request_id,
      submitted: correctedOutcome.submitted, scope_authorized: correctedOutcome.scope_authorized },
    followup: { message_id: chat.accepted.message_id, run_id: chatRun.run_id,
      session_id: chat.session_id,
      run_status: chatRun.status, answer: chat.answer, boundary_unchanged: unchanged,
      before: beforeChat, after: afterChat },
    request_id_chain: [initialReceipt.request_id, correctedRequest.request_id, correctedReceipt.request_id],
    network,
  };
  await writeFile(path.join(screenshotDir, 'browser-trace.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify(result));
} finally {
  await context.close();
  await browser.close();
}
