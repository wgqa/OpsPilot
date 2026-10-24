import { mkdir, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';

const frontendRoot = process.env.OPSPILOT_FRONTEND_ROOT;
if (!frontendRoot) throw new Error('OPSPILOT_FRONTEND_ROOT is required.');
const frontendRequire = createRequire(path.resolve(frontendRoot, 'package.json'));
const { chromium, expect } = frontendRequire('@playwright/test');

const baseURL = process.env.OPSPILOT_UI_BASE_URL ?? 'http://127.0.0.1:5178';
const outputDir = process.env.OPSPILOT_HF01_WEB_EVIDENCE;
if (!outputDir) throw new Error('OPSPILOT_HF01_WEB_EVIDENCE is required.');
await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const http = [];
const consoleErrors = [];
const journey = { browser: 'Microsoft Edge via Playwright', baseURL, steps: [], http };
page.on('response', (response) => {
  const url = new URL(response.url());
  if (url.pathname.startsWith('/api/')) {
    http.push({ method: response.request().method(), path: url.pathname, status: response.status() });
  }
});
page.on('console', (message) => {
  if (message.type() === 'error') consoleErrors.push(message.text().slice(0, 240));
});

async function waitRun(runId) {
  await expect.poll(async () => page.evaluate(async (id) => {
    const response = await fetch(`/api/runs/${encodeURIComponent(id)}`);
    if (!response.ok) return `HTTP_${response.status}`;
    return (await response.json()).status;
  }, runId), { timeout: 300000, intervals: [500, 1000, 2000, 4000] }).toBe('SUCCEEDED');
  return page.evaluate(async (id) => fetch(`/api/runs/${encodeURIComponent(id)}`).then((r) => r.json()), runId);
}

async function sendFollowup(label, body, screenshotName) {
  const messageResponse = page.waitForResponse((response) => response.request().method() === 'POST'
    && new URL(response.url()).pathname.endsWith('/messages'));
  const assessmentResponsePromise = page.waitForResponse((response) => response.request().method() === 'POST'
    && new URL(response.url()).pathname.endsWith('/investigation-updates/proposals'));
  await page.getByTestId('message-input').fill(body);
  await page.getByRole('button', { name: '发送消息' }).click();
  const acceptedResponse = await messageResponse;
  if (!acceptedResponse.ok()) throw new Error(`${label} message POST returned ${acceptedResponse.status()}.`);
  const accepted = await acceptedResponse.json();
  const assessmentResponse = await assessmentResponsePromise;
  if (!assessmentResponse.ok()) throw new Error(`${label} assessment returned ${assessmentResponse.status()}.`);
  const assessment = await assessmentResponse.json();
  const selectedRun = assessment.follow_up_action === 'INVESTIGATE'
    ? assessment.investigation_run_id : accepted.run_id;
  const run = await waitRun(selectedRun);
  const sourceChatRun = await page.evaluate(async (id) => {
    const response = await fetch(`/api/runs/${encodeURIComponent(id)}`);
    return response.ok ? response.json() : { status: `HTTP_${response.status}` };
  }, accepted.run_id);
  if (assessment.follow_up_action === 'INVESTIGATE') {
    await expect(page.getByTestId(`readonly-followup-${selectedRun}`)).toBeVisible({ timeout: 30000 });
  } else {
    await expect.poll(async () => page.evaluate(async (id) => {
      const response = await fetch(`/api/runs/${encodeURIComponent(id)}`);
      return response.ok ? (await response.json()).status : `HTTP_${response.status}`;
    }, selectedRun), { timeout: 30000 }).toBe('SUCCEEDED');
  }
  await page.screenshot({ path: path.join(outputDir, screenshotName), fullPage: true });
  const result = {
    label,
    user_message: body,
    message_id: accepted.message_id,
    source_chat_run_id: accepted.run_id,
    source_chat_run_status: sourceChatRun.status,
    intent: assessment.intent,
    follow_up_action: assessment.follow_up_action,
    assessment_id: assessment.assessment_id,
    classifier_attempt_id: assessment.attempt_id,
    investigation_run_id: assessment.investigation_run_id ?? null,
    consumed_run: run,
    screenshot: screenshotName,
  };
  journey.steps.push(result);
  return result;
}

try {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('演示身份').selectOption('support-a');
  await page.getByLabel('本地口令').fill('support-test-password');
  await page.getByRole('button', { name: '登录工作台' }).click();
  await expect(page.locator('.rail-footer')).toBeVisible({ timeout: 20000 });
  if (await page.getByRole('button', { name: '创建第一个会话' }).count()) {
    await page.getByRole('button', { name: '创建第一个会话' }).click();
  } else {
    await page.locator('.new-session-button').click();
  }
  await expect(page.locator('[data-testid="conversation"]')).toBeVisible();
  await page.screenshot({ path: path.join(outputDir, '00-empty-session.png'), fullPage: true });

  await page.getByRole('button', { name: '新建调查任务' }).first().click();
  await page.getByTestId('investigation-kind').selectOption('ASYNC_CALLBACK');
  const orderSelect = page.getByTestId('s3-order-resource');
  await expect(orderSelect.locator('option[value="async-order"]')).toBeAttached({ timeout: 15000 });
  await orderSelect.selectOption('async-order');
  const orderId = await orderSelect.inputValue();
  if (!orderId) throw new Error('No authorized pre-registered S3 order was selected.');
  await page.getByTestId('initial-symptom-input').fill(
    `订单 ${orderId} 查询成功，但下游好像没有完成回调处理，请调查当前绑定事实。`,
  );
  const createResponsePromise = page.waitForResponse((response) => response.request().method() === 'POST'
    && new URL(response.url()).pathname.endsWith('/tasks'));
  await page.getByRole('button', { name: '确认订单并启动调查' }).click();
  const createResponse = await createResponsePromise;
  if (!createResponse.ok()) throw new Error(`S3 task create returned ${createResponse.status()}.`);
  const created = await createResponse.json();
  const initialRun = await waitRun(created.run_id);
  const inspector = await page.evaluate(async (id) => fetch(`/api/tasks/${encodeURIComponent(id)}/inspector`).then((r) => r.json()), created.task_id);
  journey.session_id = await page.evaluate(async () => (await fetch('/api/sessions')).json().then((v) => v.items[0].session_id));
  journey.task_id = created.task_id;
  journey.order_id = orderId;
  journey.initial_run = initialRun;
  journey.initial_outcome = inspector.trusted_state.s3_outcome ?? null;
  if (journey.initial_outcome?.outcome !== 'RECEIVER_PROCESSING_UNCONFIRMED') {
    throw new Error(`Expected bound v2 async-order to diagnose receiver processing; got ${journey.initial_outcome?.outcome ?? 'none'}.`);
  }
  await page.screenshot({ path: path.join(outputDir, '01-s3-diagnosis.png'), fullPage: true });

  const first = await sendFollowup(
    'knowledge-probe',
    '请按当前绑定的协议版本核对 HTTP 202 的含义，查找能支持说明的当前资料并给出来源。',
    '02-knowledge-followup.png',
  );
  const second = await sendFollowup(
    'pronoun-explanation',
    '你刚才引用的那份协议，为什么不能证明接收方已经处理完成？',
    '03-pronoun-explanation.png',
  );
  const third = await sendFollowup(
    'current-receiver-state',
    '那现在接收方完成了吗？请用当前这轮新取证核实；如果没有足够事实，请明确说出缺口。',
    '04-current-state-followup.png',
  );
  journey.console_errors = consoleErrors;
  journey.result = 'BROWSER_FLOW_COMPLETED';
  journey.expectation_observation = {
    first_followup_route: first.follow_up_action,
    pronoun_followup_route: second.follow_up_action,
    current_state_route: third.follow_up_action,
    note: 'Provider choices are recorded as observed; no tool order was asserted by the test.',
  };
  await writeFile(path.join(outputDir, 'journey.json'), `${JSON.stringify(journey, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify({ status: 'PASS', task_id: created.task_id, session_id: journey.session_id,
    order_id: orderId, steps: journey.steps.map(({ label, follow_up_action, investigation_run_id, source_chat_run_id }) =>
      ({ label, follow_up_action, investigation_run_id, source_chat_run_id })), console_errors: consoleErrors.length }));
} catch (error) {
  journey.result = 'FAIL';
  journey.error = String(error?.stack ?? error);
  journey.console_errors = consoleErrors;
  await writeFile(path.join(outputDir, 'journey-failure.json'), `${JSON.stringify(journey, null, 2)}\n`, 'utf8');
  throw error;
} finally {
  await browser.close();
}
