import { access, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium, expect } from '@playwright/test';

const baseURL = process.env.OPSPILOT_M403_UI_URL;
const password = process.env.OPSPILOT_M403_SUPPORT_PASSWORD;
const screenshots = process.env.OPSPILOT_M403_SCREENSHOTS;
const resultPath = process.env.OPSPILOT_M403_RESULT_PATH;
const stagePath = process.env.OPSPILOT_M403_STAGE_PATH;
const signalPath = process.env.OPSPILOT_M403_SIGNAL_PATH;
await mkdir(screenshots, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1120 } });
const http = [];
let handoffRequest = null;
let handoffCsrf = null;
let restartRecoveryPolls = 0;
let restartPageRefreshAttempts = 0;
page.on('response', response => {
  const url = new URL(response.url());
  if (url.pathname.startsWith('/api/')) http.push({ method: response.request().method(), path: url.pathname, status: response.status() });
});
page.on('request', request => {
  const url = new URL(request.url());
  if (url.pathname.endsWith('/s3-handoff/submit') && request.method() === 'POST') {
    handoffRequest = JSON.parse(request.postData() ?? '{}');
    void request.allHeaders().then(headers => { handoffCsrf = headers['x-csrf-token'] ?? null; });
  }
});
page.on('dialog', dialog => dialog.accept());

const get = url => page.evaluate(async url => {
  const response = await fetch(url);
  return { status: response.status, body: await response.json() };
}, url);
const waitRun = async id => {
  await expect.poll(async () => (await get(`/api/runs/${id}`)).body.status,
    { timeout: 240000, intervals: [500, 1000, 2000] }).not.toMatch(/^(QUEUED|RUNNING|INTERRUPTED_RECOVERABLE)$/);
  const result = (await get(`/api/runs/${id}`)).body;
  expect(result.status).toBe('SUCCEEDED');
  return result;
};
const login = async () => {
  if (await page.locator('.rail-footer').isVisible().catch(() => false)) return;
  await page.getByLabel('演示身份').selectOption('support-a');
  await page.getByLabel('本地口令').fill(password);
  await page.getByRole('button', { name: '登录工作台' }).click();
  await expect(page.locator('.rail-footer')).toBeVisible({ timeout: 20000 });
};
const saveStage = async stage => writeFile(stagePath, JSON.stringify(stage, null, 2), 'utf8');
const waitSignal = async () => {
  const deadline = Date.now() + 480000;
  while (Date.now() < deadline) {
    try { return JSON.parse(await readFile(signalPath, 'utf8')); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  throw new Error('Timed out waiting for the isolated S3 test setup signal');
};
const waitForApiHealth = async () => {
  await expect.poll(async () => {
    restartRecoveryPolls += 1;
    return page.evaluate(async () => {
      try { return (await fetch('/api/health')).status; }
      catch { return 0; }
    });
  }, { timeout: 30000, intervals: [250, 500, 1000] }).toBe(200);
};

try {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await login();
  const catalog = await get('/api/s3/order-resources');
  expect(catalog.status).toBe(200);
  expect(catalog.body.items.map(item => item.order_id)).toContain('async-order-2');
  await page.locator('.new-session-button').click();
  await page.getByRole('button', { name: '新建调查任务' }).first().click();
  await page.getByTestId('investigation-kind').selectOption('ASYNC_CALLBACK');
  await page.getByTestId('s3-order-resource').selectOption('async-order-2');
  await page.getByTestId('initial-symptom-input').fill('订单接口返回 200，但下游没有收到异步回调。请核实当前订单和回调事件，不要重发。');
  await page.screenshot({ path: path.join(screenshots, '01-confirm-bound-order.png'), fullPage: true });
  const createResponse = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/tasks'));
  await page.getByRole('button', { name: /确认订单并启动调查/ }).click();
  const accepted = await createResponse;
  expect(accepted.status()).toBe(202);
  const created = await accepted.json();
  await waitRun(created.run_id);
  await expect(page.getByTestId('s3-diagnosis')).toBeVisible({ timeout: 30000 });
  const first = (await get(`/api/tasks/${created.task_id}/s3-handoff`)).body;
  expect(first.diagnosis_receipt.outcome).toBe('ORDER_PROCESSING');
  expect(first.diagnosis_receipt.handoff_allowed).toBe(false);
  expect(first.diagnosis_receipt.order_id).toBe('async-order-2');
  await page.screenshot({ path: path.join(screenshots, '02-first-live-evidence.png'), fullPage: true });
  await saveStage({ stage: 'FIRST_DIAGNOSIS_READY', task_id: created.task_id, session_id: created.session_id,
    run_id: created.run_id, outcome: first.diagnosis_receipt.outcome, control_revision: first.diagnosis_receipt.control_revision });
  await waitSignal();

  await page.getByTestId('critical-correction-input').fill('正式更正：之前把订单状态说错了。请重新核对同一订单当前的完成状态和回调投递证据；以服务端事实为准。');
  const correctionResponse = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/messages'));
  await page.getByTestId('submit-critical-correction').click();
  const correction = await correctionResponse;
  expect(correction.status()).toBe(202);
  const correctionAccepted = await correction.json();
  await waitRun(correctionAccepted.run_id);
  const corrected = (await get(`/api/tasks/${created.task_id}/s3-handoff`)).body;
  expect(corrected.business_outcome).toBe('HANDOFF_READY');
  expect(corrected.diagnosis_receipt.outcome).toBe('CALLBACK_DELIVERY_FAILED');
  expect(corrected.diagnosis_receipt.handling_direction).toBe('CONTACT_CALLBACK_OPERATOR');
  expect(corrected.diagnosis_receipt.currentness).toBe('CURRENT');
  await expect(page.getByTestId('submit-s3-handoff')).toBeVisible({ timeout: 30000 });
  await page.screenshot({ path: path.join(screenshots, '03-corrected-fresh-investigation.png'), fullPage: true });

  const handoffResponse = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith('/s3-handoff/submit'));
  await page.getByTestId('submit-s3-handoff').click();
  const submitted = await handoffResponse;
  expect(submitted.status()).toBe(202);
  const handoff = await submitted.json();
  await expect(page.getByTestId('s3-handoff-receipt')).toBeVisible({ timeout: 30000 });
  expect(handoff.business_outcome).toBe('HANDOFF_ACCEPTED');
  expect(handoff.replayed).toBe(false);
  expect(handoffRequest?.operation_id).toBe(handoff.operation_id);
  expect(handoffCsrf).toBeTruthy();
  const replay = await page.evaluate(async ({ taskId, body, csrf }) => {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/s3-handoff/submit`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf,
        'Idempotency-Key': body.operation_id }, body: JSON.stringify(body),
    });
    return { status: response.status, body: await response.json() };
  }, { taskId: created.task_id, body: handoffRequest, csrf: handoffCsrf });
  expect(replay.status).toBe(200);
  expect(replay.body.replayed).toBe(true);
  expect(replay.body.receipt_id).toBe(handoff.receipt_id);
  await page.screenshot({ path: path.join(screenshots, '04-handoff-accepted-receipt.png'), fullPage: true });
  await saveStage({ stage: 'HANDOFF_COMMITTED_WAIT_FOR_API_RESTART', task_id: created.task_id,
    session_id: created.session_id, run_id: correctionAccepted.run_id, receipt_id: handoff.receipt_id });
  await waitSignal();

  await waitForApiHealth();
  await expect.poll(async () => {
    try {
      const persisted = await get(`/api/tasks/${created.task_id}/s3-handoff`);
      return persisted.status === 200 ? persisted.body.handoff_receipt?.receipt_id ?? null : null;
    } catch { return null; }
  }, { timeout: 30000, intervals: [250, 500, 1000] }).toBe(handoff.receipt_id);
  const sessionItem = page.locator('.session-item').filter({ hasText: created.session_id.slice(0, 22) });
  let restoredReceipt = false;
  for (let refreshAttempt = 1; refreshAttempt <= 2 && !restoredReceipt; refreshAttempt += 1) {
    restartPageRefreshAttempts = refreshAttempt;
    await page.reload({ waitUntil: 'domcontentloaded' });
    await login();
    await expect(sessionItem).toBeVisible({ timeout: 20000 });
    await sessionItem.click();
    try {
      await expect(page.getByTestId('s3-handoff-receipt'))
        .toContainText(handoff.receipt_id, { timeout: 8000 });
      restoredReceipt = true;
    } catch (error) {
      if (refreshAttempt === 2) throw error;
      await waitForApiHealth();
    }
  }
  expect(restoredReceipt).toBe(true);
  await expect.poll(async () => page.evaluate(async taskId => {
    try {
      const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/s3-handoff`);
      if (!response.ok) return { status: response.status };
      return await response.json();
    } catch { return { status: 0 }; }
  }, created.task_id), { timeout: 30000, intervals: [250, 500, 1000] }).toMatchObject({
    business_outcome: 'HANDOFF_ACCEPTED',
  });
  const afterRestartValue = (await get(`/api/tasks/${created.task_id}/s3-handoff`)).body;
  expect(afterRestartValue.handoff_receipt.receipt_id).toBe(handoff.receipt_id);
  await page.screenshot({ path: path.join(screenshots, '05-after-api-restart.png'), fullPage: true });

  const followupBody = '这个 HANDOFF_ACCEPTED 回执说明订单和回调已经恢复了吗？请依据持久回执说明当前处理状态。';
  await page.getByTestId('message-input').fill(followupBody);
  let acceptedFollowup = null;
  for (let attempt = 0; attempt < 3 && !acceptedFollowup; attempt += 1) {
    const followupResponse = page.waitForResponse(r => r.request().method() === 'POST'
      && new URL(r.url()).pathname.endsWith('/messages'));
    await page.getByRole('button', { name: '发送消息' }).click();
    const response = await followupResponse;
    if (response.status() === 202) {
      acceptedFollowup = await response.json();
      break;
    }
    await waitForApiHealth();
    const messages = (await get(`/api/sessions/${created.session_id}/messages?limit=500`)).body.items;
    const persisted = messages.find(item => item.role === 'USER' && item.body === followupBody);
    if (persisted) {
      const runs = (await get(`/api/sessions/${created.session_id}/runs`)).body.items;
      const matching = runs.find(item => item.source_message_id === persisted.message_id);
      if (matching) acceptedFollowup = { run_id: matching.run_id, message_id: persisted.message_id };
      break;
    }
  }
  expect(acceptedFollowup, 'follow-up must be accepted or found by persisted message identity').toBeTruthy();
  await waitRun(acceptedFollowup.run_id);
  const answer = await page.locator('.message-row.assistant').last().innerText();
  expect(answer).toMatch(/HANDOFF_ACCEPTED|本地队列已接收|队列已接收/);
  expect(answer).toContain(handoff.receipt_id);
  expect(answer).not.toMatch(/没有任何 `?HANDOFF_ACCEPTED`? 回执|没有看到 `?HANDOFF_ACCEPTED`? 类型的持久回执/);
  const afterFollowup = (await get(`/api/tasks/${created.task_id}/s3-handoff`)).body;
  expect(afterFollowup.business_outcome).toBe('HANDOFF_ACCEPTED');
  expect(afterFollowup.handoff_receipt.receipt_id).toBe(handoff.receipt_id);
  const inspector = (await get(`/api/tasks/${created.task_id}/inspector`)).body;
  const result = { status: 'PASS', browser: 'Microsoft Edge real browser', task_id: created.task_id,
    session_id: created.session_id, order_id: 'async-order-2', first_diagnosis: first.diagnosis_receipt,
    critical_correction: { message_id: correctionAccepted.message_id, run_id: correctionAccepted.run_id,
      control_revision_after: corrected.diagnosis_receipt.control_revision, diagnosis: corrected.diagnosis_receipt },
    handoff, duplicate_confirmation: replay, after_api_restart: afterRestartValue,
    followup: { run_id: acceptedFollowup.run_id, answer, outcome_unchanged: afterFollowup.business_outcome },
    final_inspector: inspector, restart_recovery_polls: restartRecoveryPolls,
    restart_page_refresh_attempts: restartPageRefreshAttempts, http };
  await page.screenshot({ path: path.join(screenshots, '06-result-followup.png'), fullPage: true });
  await writeFile(resultPath, JSON.stringify(result, null, 2), 'utf8');
  await saveStage({ stage: 'COMPLETE', task_id: created.task_id, receipt_id: handoff.receipt_id });
  console.log(JSON.stringify({ status: 'PASS', task_id: created.task_id, receipt_id: handoff.receipt_id,
    correction_run_id: correctionAccepted.run_id, followup_run_id: acceptedFollowup.run_id }));
} catch (error) {
  await page.screenshot({ path: path.join(screenshots, 'failure.png'), fullPage: true }).catch(() => {});
  await writeFile(resultPath, JSON.stringify({ status: 'FAIL', message: error.message, http }, null, 2), 'utf8');
  throw error;
} finally {
  await browser.close();
}
