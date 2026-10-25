import { mkdir, writeFile, readFile } from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(path.resolve(process.cwd(), 'frontend/package.json'));
const { chromium, expect } = require('@playwright/test');
const baseURL = process.env.OPSPILOT_UI_BASE_URL;
const sessionId = process.env.OPSPILOT_EG01_SESSION_ID;
const targetTaskId = process.env.OPSPILOT_EG01_TARGET_TASK_ID;
const runId = process.env.OPSPILOT_EG01_TARGET_RUN_ID;
const sourceTaskId = process.env.OPSPILOT_EG01_SOURCE_TASK_ID;
const memoryId = process.env.OPSPILOT_EG01_MEMORY_ID;
const password = process.env.OPSPILOT_EG01_SUPPORT_PASSWORD;
const outputDir = process.env.OPSPILOT_EVIDENCE_SCREENSHOTS;
if (![baseURL, sessionId, targetTaskId, runId, sourceTaskId, memoryId, password, outputDir].every(Boolean)) {
  throw new Error('M4-EG-01 persisted Web revisit configuration is incomplete; secrets are not written to evidence.');
}

const seed = JSON.parse(await readFile(process.env.OPSPILOT_EG01_WEB_SEED, 'utf8'));
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const requests = [];
page.on('response', (response) => {
  const url = new URL(response.url());
  if (url.pathname.startsWith('/api/')) requests.push({
    method: response.request().method(), path: url.pathname, status: response.status(),
  });
});
await mkdir(outputDir, { recursive: true });
try {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('演示身份').selectOption('support-a');
  await page.getByLabel('本地口令').fill(password);
  await page.getByRole('button', { name: '登录工作台' }).click();
  await expect(page.locator('.rail-footer')).toBeVisible({ timeout: 20000 });
  await page.locator('.session-item').filter({ hasText: sessionId.slice(0, 22) }).click();
  await expect(page.getByTestId('s3-diagnosis')).toBeVisible({ timeout: 20000 });
  const inspected = await page.evaluate(async ({ task, run }) => {
    const [inspectorResponse, runResponse] = await Promise.all([
      fetch(`/api/tasks/${encodeURIComponent(task)}/inspector`),
      fetch(`/api/runs/${encodeURIComponent(run)}`),
    ]);
    return {
      inspector_status: inspectorResponse.status,
      inspector: inspectorResponse.ok ? await inspectorResponse.json() : null,
      run_status_http: runResponse.status,
      run: runResponse.ok ? await runResponse.json() : null,
    };
  }, { task: targetTaskId, run: runId });
  if (inspected.inspector_status !== 200 || inspected.run_status_http !== 200 || inspected.run?.status !== 'SUCCEEDED') {
    throw new Error(`Persisted Task/Run is unavailable or not complete: ${JSON.stringify({
      inspector: inspected.inspector_status, run: inspected.run_status_http, status: inspected.run?.status,
    })}`);
  }
  const provenance = inspected.inspector.investigator_context_provenance ?? [];
  const memoryCalls = provenance.filter((item) => (item.selected_memories ?? []).some((memory) =>
    memory.memory_id === memoryId && memory.source_task_id === sourceTaskId));
  if (memoryCalls.length === 0) throw new Error('Persisted Task B has no model call provenance for the approved Task A Memory.');
  const diagnosis = await page.getByTestId('s3-diagnosis').innerText();
  await page.screenshot({ path: path.join(outputDir, '06-task-b-persisted-result.png'), fullPage: true });
  const result = {
    status: 'BROWSER_REPLAYED_PERSISTED_TASK',
    seed_release: seed.release_id,
    session_id: sessionId,
    source_task_id: sourceTaskId,
    target_task_id: targetTaskId,
    target_run_id: runId,
    run_status: inspected.run.status,
    current_s3_outcome: inspected.inspector.trusted_state?.s3_outcome ?? null,
    model_calls: provenance.map((item) => ({
      call_id: item.call_id,
      model_status: item.model_status,
      selected_memory_ids: (item.selected_memories ?? []).map((memory) => memory.memory_id),
      excluded_sources: item.excluded_sources ?? [],
      prompt_digest: item.prompt_digest,
      built_at: item.built_at,
    })),
    task_a_memory_selected_calls: memoryCalls.map((item) => item.call_id),
    visible_diagnosis: diagnosis,
    currentness_at_revisit: inspected.inspector.trusted_state?.s3_outcome?.currentness ?? null,
    web_requests: requests,
    screenshot: '06-task-b-persisted-result.png',
    model_called_during_revisit: false,
    user_credentials_logged: false,
  };
  await writeFile(path.join(outputDir, 'WEB-REVISIT.json'), JSON.stringify(result, null, 2), 'utf8');
  console.log(JSON.stringify({
    status: result.status,
    run_status: result.run_status,
    target_outcome: result.current_s3_outcome?.outcome,
    currentness: result.currentness_at_revisit,
    memory_selected_calls: result.task_a_memory_selected_calls,
    web_requests: result.web_requests.length,
    model_called: result.model_called_during_revisit,
  }, null, 2));
} finally {
  await context.close();
  await browser.close();
}
