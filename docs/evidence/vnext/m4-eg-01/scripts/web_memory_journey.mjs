import { mkdir, writeFile, readFile } from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(path.resolve(process.cwd(), 'frontend/package.json'));
const { chromium, expect } = require('@playwright/test');

const baseURL = process.env.OPSPILOT_UI_BASE_URL;
const apiURL = process.env.OPSPILOT_EG01_API_ORIGIN;
const supportPassword = process.env.OPSPILOT_EG01_SUPPORT_PASSWORD;
const approverPassword = process.env.OPSPILOT_EG01_APPROVER_PASSWORD;
const seedPath = process.env.OPSPILOT_EG01_WEB_SEED;
const outputDir = process.env.OPSPILOT_EVIDENCE_SCREENSHOTS;
if (!baseURL || !apiURL || !supportPassword || !approverPassword || !seedPath || !outputDir) {
  throw new Error('M4-EG-01 Web journey configuration is incomplete; secret values are never written to evidence.');
}

const seed = JSON.parse(await readFile(seedPath, 'utf8'));
const records = [];
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const supportContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const supportPage = await supportContext.newPage();
supportPage.on('response', (response) => {
  const url = new URL(response.url());
  if (url.pathname.startsWith('/api/')) records.push({
    role: 'support-a', method: response.request().method(), path: url.pathname, status: response.status(),
  });
});
const approverContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const approverPage = await approverContext.newPage();
approverPage.on('response', (response) => {
  const url = new URL(response.url());
  if (url.pathname.startsWith('/api/')) records.push({
    role: 'approver-a', method: response.request().method(), path: url.pathname, status: response.status(),
  });
});

async function login(page, actor, password) {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('演示身份').selectOption(actor);
  await page.getByLabel('本地口令').fill(password);
  await page.getByRole('button', { name: '登录工作台' }).click();
  await expect(page.locator(actor.startsWith('approver-')
    ? '[data-testid="memory-approval-center"]' : '.rail-footer')).toBeVisible({ timeout: 20000 });
}

const screenshot = async (page, name) => page.screenshot({ path: path.join(outputDir, name), fullPage: true });
await mkdir(outputDir, { recursive: true });
let journey;
let sourceCheck = null;
try {
  const sourceTaskId = seed.source_task.task_id;
  const sourceSessionId = seed.source_session_id;
  const sourceRunId = seed.source_task.run_id;
  const sourceOrderId = 'eg01-web-source';
  const targetOrderId = 'eg01-web-target';

  await login(supportPage, 'support-a', supportPassword);
  const sessionButton = supportPage.locator('.session-item').filter({ hasText: sourceSessionId.slice(0, 22) });
  await sessionButton.click();
  await expect(supportPage.getByTestId('s3-diagnosis')).toBeVisible({ timeout: 20000 });
  sourceCheck = await supportPage.evaluate(async (taskId) => {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/inspector`);
    const body = response.ok ? await response.json() : null;
    return { http_status: response.status, outcome: body?.trusted_state?.s3_outcome ?? null };
  }, sourceTaskId);
  if (sourceCheck.http_status !== 200 || sourceCheck.outcome?.currentness !== 'CURRENT') {
    throw new Error(`Task A source is not current at the Web action boundary: ${JSON.stringify(sourceCheck)}`);
  }
  await screenshot(supportPage, '01-task-a-source-ready.png');
  await expect(supportPage.getByTestId('create-memory-candidate')).toBeVisible({ timeout: 30000 });

  const candidateResponsePromise = supportPage.waitForResponse((response) =>
    response.request().method() === 'POST'
      && new URL(response.url()).pathname === `/api/tasks/${encodeURIComponent(sourceTaskId)}/memories/candidates`);
  await supportPage.getByTestId('create-memory-candidate').click();
  const candidateResponse = await candidateResponsePromise;
  if (!candidateResponse.ok()) throw new Error(`Memory candidate request returned HTTP ${candidateResponse.status()}.`);
  const candidate = await candidateResponse.json();
  await expect(supportPage.getByText(/真实来源候选已建立/)).toBeVisible({ timeout: 15000 });
  await screenshot(supportPage, '02-task-a-candidate-created.png');

  await login(approverPage, 'approver-a', approverPassword);
  const candidateButton = approverPage.getByTestId(`memory-candidate-${candidate.memory_id}`);
  await expect(candidateButton).toBeVisible({ timeout: 30000 });
  await candidateButton.click();
  await screenshot(approverPage, '03-approver-candidate-review.png');
  approverPage.on('dialog', (dialog) => dialog.accept());
  const approvalResponsePromise = approverPage.waitForResponse((response) =>
    response.request().method() === 'POST'
      && new URL(response.url()).pathname === `/api/memories/${encodeURIComponent(candidate.memory_id)}/confirm`);
  await approverPage.getByTestId('confirm-memory').click();
  const approvalResponse = await approvalResponsePromise;
  if (!approvalResponse.ok()) throw new Error(`Memory approval returned HTTP ${approvalResponse.status()}.`);
  const approval = await approvalResponse.json();
  await expect(approverPage.getByTestId('revoke-memory')).toBeVisible({ timeout: 15000 });
  await screenshot(approverPage, '04-approver-memory-active.png');

  await supportPage.reload({ waitUntil: 'domcontentloaded' });
  await expect(supportPage.locator('.rail-footer')).toBeVisible({ timeout: 20000 });
  await supportPage.locator('.session-item').filter({ hasText: sourceSessionId.slice(0, 22) }).click();
  await supportPage.getByRole('button', { name: '新建调查任务', exact: true }).click();
  await supportPage.getByTestId('investigation-kind').selectOption('ASYNC_CALLBACK');
  await expect(supportPage.getByTestId('s3-order-resource')).toBeEnabled({ timeout: 15000 });
  await supportPage.getByTestId('s3-order-resource').selectOption(targetOrderId);
  const targetInput = '订单接口返回 HTTP 200，但下游没有收到异步回调。上次我们遇到过类似的回调问题，这次是不是也一样？能参考之前确认的处理经验帮我调查吗？请核实当前选定订单的事件，不要重发。';
  await supportPage.getByTestId('initial-symptom-input').fill(targetInput);
  const taskResponsePromise = supportPage.waitForResponse((response) =>
    response.request().method() === 'POST'
      && new URL(response.url()).pathname === `/api/sessions/${encodeURIComponent(sourceSessionId)}/tasks`);
  await supportPage.getByRole('button', { name: /确认订单并启动调查/ }).click();
  const taskResponse = await taskResponsePromise;
  if (!taskResponse.ok()) throw new Error(`Task B creation returned HTTP ${taskResponse.status()}.`);
  const targetTask = await taskResponse.json();

  await expect.poll(async () => supportPage.evaluate(async (runId) => {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
    return response.ok ? (await response.json()).status : `HTTP_${response.status}`;
  }, targetTask.run_id), { timeout: 240000, intervals: [500, 1000, 2000] }).toBe('SUCCEEDED');
  await expect(supportPage.getByTestId('s3-diagnosis')).toBeVisible({ timeout: 30000 });
  const inspectorResponse = await supportPage.evaluate(async (taskId) => {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/inspector`);
    return { status: response.status, body: response.ok ? await response.json() : null };
  }, targetTask.task_id);
  const visibleDiagnosis = await supportPage.getByTestId('s3-diagnosis').innerText();
  const memoryContextCalls = (inspectorResponse.body?.investigator_context_provenance ?? []).filter((call) =>
    (call.selected_memories ?? []).some((memory) =>
      memory.memory_id === candidate.memory_id && memory.source_task_id === sourceTaskId));
  if (memoryContextCalls.length === 0) {
    throw new Error('Task B has no actual model call provenance for the Memory approved from Task A.');
  }
  const selectedMemoryText = JSON.stringify(memoryContextCalls.map((call) => ({
    call_id: call.call_id, prompt_digest: call.prompt_digest,
    model_status: call.model_status, built_at: call.built_at,
  })));
  await screenshot(supportPage, '05-task-b-real-investigation.png');

  journey = {
    status: 'BROWSER_JOURNEY_COMPLETED',
    source: {
      task_id: sourceTaskId, session_id: sourceSessionId, run_id: sourceRunId,
      order_id: sourceOrderId, outcome: seed.source_outcome.outcome,
      currentness_at_action: sourceCheck.outcome.currentness,
      preparation_kind: seed.source_policy,
    },
    memory: {
      memory_id: candidate.memory_id, version: candidate.version, state: approval.state,
      digest: candidate.content_digest ?? approval.content_digest,
      candidate_http_status: candidateResponse.status(), approval_http_status: approvalResponse.status(),
      created_by: candidate.created_by, approved_by: approval.confirmed_by,
    },
    target: {
      task_id: targetTask.task_id, session_id: sourceSessionId, run_id: targetTask.run_id,
      order_id: targetOrderId, input: targetInput, run_status: 'SUCCEEDED',
      inspector_http_status: inspectorResponse.status,
      outcome: inspectorResponse.body?.trusted_state?.s3_outcome ?? null,
      selected_memory_provenance: selectedMemoryText,
      memory_context_calls: memoryContextCalls.map((call) => call.call_id),
      diagnosis_visible_in_browser: visibleDiagnosis,
      no_claim_of_recovery: visibleDiagnosis.includes('未重发') || visibleDiagnosis.includes('未宣称业务恢复'),
    },
    web_requests: records,
    screenshots: [
      '01-task-a-source-ready.png', '02-task-a-candidate-created.png',
      '03-approver-candidate-review.png', '04-approver-memory-active.png',
      '05-task-b-real-investigation.png',
    ],
    api_origin: apiURL,
    user_credentials_logged: false,
  };
  await writeFile(path.join(outputDir, 'WEB-JOURNEY.json'), JSON.stringify(journey, null, 2), 'utf8');
} catch (error) {
  const failure = {
    status: 'FAIL', message: String(error?.stack ?? error), web_requests: records,
    source_seed_path: seedPath, source_check: sourceCheck, user_credentials_logged: false,
  };
  await writeFile(path.join(outputDir, 'WEB-JOURNEY-FAILURE.json'), JSON.stringify(failure, null, 2), 'utf8');
  throw error;
} finally {
  await approverContext.close();
  await supportContext.close();
  await browser.close();
}

console.log(JSON.stringify({
  status: journey.status,
  sourceTask: journey.source.task_id,
  memoryId: journey.memory.memory_id,
  targetTask: journey.target.task_id,
  targetRun: journey.target.run_id,
  targetOutcome: journey.target.outcome?.outcome,
  apiRequests: journey.web_requests.length,
  screenshots: journey.screenshots,
}, null, 2));
