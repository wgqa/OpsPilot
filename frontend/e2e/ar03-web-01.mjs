import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const baseURL = process.env.OPSPILOT_UI_BASE_URL ?? 'http://127.0.0.1:5178/';
const mode = process.env.AR03_WEB_MODE;
const evidenceDir = process.env.AR03_WEB_EVIDENCE_DIR;
const targetSession = process.env.AR03_WEB_SESSION_ID;
const targetMessage = process.env.AR03_WEB_MESSAGE_ID;
const targetRun = process.env.AR03_WEB_RUN_ID;
const localPassword = process.env.AR03_WEB_LOCAL_PASSWORD;
const screenshotDir = path.join(evidenceDir, 'screenshots');
const records = [];

if (!mode || !evidenceDir) throw new Error('AR03 web test requires mode and evidence directory.');
if (!localPassword) throw new Error('AR03_WEB_LOCAL_PASSWORD is required for the local demo login.');
await mkdir(screenshotDir, { recursive: true });
const promptDoc = JSON.parse(await readFile(
  new URL('../../docs/evidence/ar-03-real-llm-01-prep/CASES.json', import.meta.url), 'utf8',
));
const frozenPrompt = promptDoc.prompt;
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1040 }, deviceScaleFactor: 1 });
const page = await context.newPage();
page.on('request', (request) => {
  const url = new URL(request.url());
  if (url.pathname.startsWith('/api/')) {
    records.push({ type: 'request', method: request.method(), path: url.pathname });
  }
});
page.on('response', (response) => {
  const url = new URL(response.url());
  if (url.pathname.startsWith('/api/')) {
    records.push({ type: 'response', method: response.request().method(), path: url.pathname, status: response.status() });
  }
});
page.on('console', (message) => {
  if (message.type() === 'error') records.push({ type: 'console_error', text: message.text().slice(0, 240) });
});

async function login() {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('演示身份').selectOption('support-a');
  await page.getByLabel('本地口令').fill(localPassword);
  await page.getByRole('button', { name: '登录工作台' }).click();
  await expect(page.locator('.rail-footer')).toContainText('support-a', { timeout: 15000 });
}

async function api(pathname) {
  const result = await page.evaluate(async (url) => {
    const response = await fetch(url);
    return { status: response.status, body: await response.json() };
  }, pathname);
  if (result.status !== 200) throw new Error(`API ${pathname} returned ${result.status}`);
  return result.body;
}

async function apiStatus(pathname) {
  return page.evaluate(async (url) => {
    const response = await fetch(url);
    return { status: response.status, body: await response.text() };
  }, pathname);
}

async function selectSession(sessionId) {
  const button = page.locator('.session-item').filter({ hasText: sessionId.slice(0, 22) }).first();
  await expect(button).toBeVisible({ timeout: 15000 });
  await button.click();
  if (sessionId === targetSession) {
    await expect(page.locator(`.conversation-thread[data-source-message-id="${targetMessage}"]`)).toBeVisible({ timeout: 20000 });
  }
}

async function inspectSavedReplay() {
  if (!targetSession || !targetMessage || !targetRun) throw new Error('Replay IDs are required.');
  await login();
  const sessions = await api('/api/sessions');
  if (!sessions.items.some((item) => item.session_id === targetSession)) throw new Error('Frozen replay session is not visible to support-a.');
  await selectSession(targetSession);
  const messagesBefore = await api(`/api/sessions/${encodeURIComponent(targetSession)}/messages`);
  const runsBefore = await api(`/api/sessions/${encodeURIComponent(targetSession)}/runs`);
  const anchor = messagesBefore.items.find((item) => item.message_id === targetMessage && item.role === 'USER');
  const answer = messagesBefore.items.find((item) => item.role === 'ASSISTANT' && item.answer_source_message_id === targetMessage);
  const run = runsBefore.items.find((item) => item.run_id === targetRun);
  if (!anchor || !answer || !run) throw new Error('Saved Message/Answer/Run relationship did not resolve through the API.');
  if (answer.answer_run_id !== targetRun || run.source_message_id !== targetMessage) {
    throw new Error('Saved replay answer and Run do not retain their explicit source-message relationship.');
  }
  if (mode === 'replay-a' && (run.status !== 'SUCCEEDED' || answer.answer_kind !== 'CHAT_MODEL')) throw new Error('Scenario A replay is not the frozen successful model answer.');
  if (mode === 'replay-b' && (run.status !== 'FAILED' || answer.answer_kind !== 'PROGRAM_LIMIT')) throw new Error('Scenario B replay is not the frozen program limit result.');

  const thread = page.locator(`.conversation-thread[data-source-message-id="${targetMessage}"]`);
  const assistant = thread.locator(`.message-row.assistant[data-run-id="${targetRun}"]`);
  await expect(assistant).toBeVisible();
  const bodyBefore = await assistant.innerText();
  const assistantCountBefore = await page.locator('.conversation-thread .message-row.assistant').count();
  const sourceDetails = assistant.locator('details.followup-sources').first();
  await sourceDetails.locator('summary').click();
  await expect.poll(() => records.some((item) => item.type === 'response' && item.path === `/api/runs/${targetRun}/assistant-sources`), { timeout: 10000 }).toBe(true);
  const sourceText = await sourceDetails.innerText();
  await page.screenshot({ path: path.join(screenshotDir, `${mode}-sources.png`), fullPage: true });
  const domBeforeReload = await page.locator('body').innerText();

  const postCountBeforeReload = records.filter((item) => item.type === 'request' && item.method === 'POST').length;
  await page.reload({ waitUntil: 'domcontentloaded' });
  await selectSession(targetSession);
  const assistantAfter = page.locator(`.conversation-thread[data-source-message-id="${targetMessage}"] .message-row.assistant[data-run-id="${targetRun}"]`);
  await expect(assistantAfter).toBeVisible();
  const bodyAfter = await assistantAfter.innerText();
  const sourceDetailsAfter = assistantAfter.locator('details.followup-sources').first();
  await sourceDetailsAfter.locator('summary').click();
  await expect.poll(() => records.filter((item) => item.type === 'response' && item.path === `/api/runs/${targetRun}/assistant-sources`).length, { timeout: 10000 }).toBeGreaterThanOrEqual(2);
  const sourceTextAfterReload = await sourceDetailsAfter.innerText();
  const messagesAfter = await api(`/api/sessions/${encodeURIComponent(targetSession)}/messages`);
  const runsAfter = await api(`/api/sessions/${encodeURIComponent(targetSession)}/runs`);
  const postCountAfterReload = records.filter((item) => item.type === 'request' && item.method === 'POST').length;
  const result = {
    mode,
    evidence_level: mode === 'replay-a' ? 'SAVED_REAL_DEEPSEEK_RESULT_READ_ONLY_REPLAY' : 'SAVED_HISTORICAL_PROGRAM_LIMIT_READ_ONLY_REPLAY',
    session_id: targetSession,
    source_message_id: targetMessage,
    answer_message_id: answer.message_id,
    answer_source_message_id: answer.answer_source_message_id,
    answer_run_id: answer.answer_run_id,
    run_id: targetRun,
    run_source_message_id: run.source_message_id,
    run_status: run.status,
    answer_kind: answer.answer_kind,
    answer_source_status: answer.source_status ?? null,
    answer_text: bodyBefore,
    answer_same_after_reload: bodyBefore === bodyAfter,
    assistant_count_before_reload: assistantCountBefore,
    assistant_count_after_reload: await page.locator('.conversation-thread .message-row.assistant').count(),
    user_message_count_before_reload: messagesBefore.items.filter((item) => item.role === 'USER').length,
    user_message_count_after_reload: messagesAfter.items.filter((item) => item.role === 'USER').length,
    run_count_before_reload: runsBefore.items.length,
    run_count_after_reload: runsAfter.items.length,
    source_detail_text: sourceText,
    source_detail_text_after_reload: sourceTextAfterReload,
    source_details_reloaded: sourceTextAfterReload === sourceText,
    screenshot: `${mode}-sources.png`,
    post_request_count_before_reload: postCountBeforeReload,
    post_request_count_after_reload: postCountAfterReload,
    reload_created_no_post: postCountBeforeReload === postCountAfterReload,
    dom_text_before_reload: domBeforeReload,
    api_events: records.slice(),
  };
  if (!result.answer_same_after_reload || result.run_count_before_reload !== result.run_count_after_reload || !result.reload_created_no_post) {
    await writeFile(path.join(evidenceDir, `${mode}-result.json`), JSON.stringify(result, null, 2) + '\n', 'utf8');
    throw new Error('Persisted replay changed or triggered a new POST during refresh.');
  }
  if (mode === 'replay-a' && answer.source_status === 'BUSINESS_SOURCE_INVALIDATED') {
    if (!bodyBefore.includes('来源已失效') || bodyBefore.includes('QUEUED')) {
      await writeFile(path.join(evidenceDir, `${mode}-result.json`), JSON.stringify(result, null, 2) + '\n', 'utf8');
      throw new Error('Expired business sources were not safely replaced by an explicit historical-source notice.');
    }
  } else if (mode === 'replay-a' && (!bodyBefore.includes('callback-retry-contract') || !bodyBefore.includes('HTTP 202') || !bodyBefore.includes('QUEUED'))) {
    await writeFile(path.join(evidenceDir, `${mode}-result.json`), JSON.stringify(result, null, 2) + '\n', 'utf8');
    throw new Error('Real saved Scenario A answer lost protocol or current business content in the UI.');
  }
  if (mode === 'replay-b' && (!bodyBefore.includes('程序限制说明') || !bodyBefore.includes('本次解释未完成'))) {
    await writeFile(path.join(evidenceDir, `${mode}-result.json`), JSON.stringify(result, null, 2) + '\n', 'utf8');
    throw new Error('Program-limit result was not distinguished from a model answer.');
  }
  await writeFile(path.join(evidenceDir, `${mode}.json`), JSON.stringify(result, null, 2) + '\n', 'utf8');
  await page.screenshot({ path: path.join(screenshotDir, `${mode}-after-reload.png`), fullPage: true });
}

async function inspectRevokedReplay() {
  if (!targetSession || !targetMessage || !targetRun) throw new Error('Revoked replay IDs are required.');
  await login();
  await selectSession(targetSession);
  const messages = await api(`/api/sessions/${encodeURIComponent(targetSession)}/messages`);
  const user = messages.items.find((item) => item.message_id === targetMessage && item.role === 'USER');
  const answer = messages.items.find((item) => item.message_id !== targetMessage && item.role === 'ASSISTANT');
  if (!user || !answer || answer.answer_run_id || answer.answer_source_message_id || answer.answer_kind) {
    throw new Error('Revoked S3 history retained an exposed answer/run/source association.');
  }
  if (!answer.body.includes('S3 受限历史回答已隐藏')) {
    throw new Error('Revoked S3 message did not receive the explicit restricted-history response.');
  }
  const sourceResponse = await apiStatus(`/api/runs/${encodeURIComponent(targetRun)}/assistant-sources`);
  if (sourceResponse.status !== 403 || !sourceResponse.body.includes('S3_SCOPE_DENIED')) {
    throw new Error(`Expected revoked-source request to be denied, got HTTP ${sourceResponse.status}.`);
  }
  const bodyBeforeReload = await page.locator('body').innerText();
  const forbiddenTextVisible = ['callback-retry-contract', 'HTTP 202', 'QUEUED'].some((text) => bodyBeforeReload.includes(text));
  if (forbiddenTextVisible) throw new Error('Protected S3 answer content reappeared in the browser after Scope revocation.');
  const postsBeforeReload = records.filter((item) => item.type === 'request' && item.method === 'POST').length;
  await page.screenshot({ path: path.join(screenshotDir, 'revoked-source-hidden.png'), fullPage: true });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await selectSession(targetSession);
  const afterReload = await api(`/api/sessions/${encodeURIComponent(targetSession)}/messages`);
  const restrictedAfterReload = afterReload.items.find((item) => item.message_id === answer.message_id);
  const sourceAfterReload = await apiStatus(`/api/runs/${encodeURIComponent(targetRun)}/assistant-sources`);
  const postsAfterReload = records.filter((item) => item.type === 'request' && item.method === 'POST').length;
  const bodyAfterReload = await page.locator('body').innerText();
  const result = {
    mode: 'revoked-replay',
    evidence_level: 'REAL_BROWSER_READ_AFTER_LOCAL_TEST_GRANT_REVOCATION',
    session_id: targetSession,
    task_id: user.task_id,
    source_message_id: targetMessage,
    answer_message_id: answer.message_id,
    run_id: targetRun,
    run_status: 'historically persisted; source endpoint denied after current grant revocation',
    message_answer_kind_exposed: answer.answer_kind,
    message_body_after_revocation: answer.body,
    source_endpoint_status: sourceResponse.status,
    source_endpoint_error: sourceResponse.body,
    source_endpoint_status_after_reload: sourceAfterReload.status,
    restricted_message_after_reload: restrictedAfterReload?.body ?? null,
    protected_content_visible: forbiddenTextVisible || ['callback-retry-contract', 'HTTP 202', 'QUEUED'].some((text) => bodyAfterReload.includes(text)),
    no_new_post_after_reload: postsBeforeReload === postsAfterReload,
    screenshot: 'revoked-source-hidden.png',
    api_events: records.slice(),
  };
  if (sourceAfterReload.status !== 403 || !result.restricted_message_after_reload?.includes('S3 受限历史回答已隐藏') || result.protected_content_visible || !result.no_new_post_after_reload) {
    await writeFile(path.join(evidenceDir, 'revoked-replay-result.json'), JSON.stringify(result, null, 2) + '\n', 'utf8');
    throw new Error('Revoked source or protected message was not kept hidden after refresh.');
  }
  await writeFile(path.join(evidenceDir, 'revoked-replay.json'), JSON.stringify(result, null, 2) + '\n', 'utf8');
  await page.screenshot({ path: path.join(screenshotDir, 'revoked-source-hidden-after-reload.png'), fullPage: true });
}

async function runDeterministicFullFlow() {
  await login();
  await page.locator('.new-session-button').click();
  await expect(page.locator('.conversation-heading h1')).toContainText('会话');
  const modeInput = page.getByTestId('professional-assistant-mode');
  if (!(await modeInput.isChecked())) await modeInput.check();
  await expect(page.getByTestId('assistant-order-open')).toBeVisible();
  const projectSelect = page.getByTestId('assistant-project');
  await expect(projectSelect).toHaveValue('orders-callback');
  const visibleProject = await projectSelect.inputValue();
  await page.getByTestId('assistant-order-open').click();
  await expect(page.getByTestId('assistant-order-form')).toBeVisible();
  const resource = page.getByTestId('assistant-order-resource');
  await expect(resource.locator('option[value="ar03-order"]')).toBeAttached();
  await resource.selectOption('ar03-order');
  const selectedOrderId = await resource.inputValue();
  await page.screenshot({ path: path.join(screenshotDir, 'deterministic-authorized-project-and-order.png'), fullPage: true });
  await page.getByTestId('assistant-order-question').fill(frozenPrompt);
  const initialPosts = records.filter((item) => item.type === 'request' && item.method === 'POST');
  await page.getByRole('button', { name: '确认订单并调查' }).click();
  await expect(page.locator('.conversation-thread .message-row.assistant')).toHaveCount(1, { timeout: 120000 });

  const sessionList = await api('/api/sessions');
  const session = sessionList.items[0];
  if (!session) throw new Error('No session exists after browser order submission.');
  const messages = await api(`/api/sessions/${encodeURIComponent(session.session_id)}/messages`);
  const runs = await api(`/api/sessions/${encodeURIComponent(session.session_id)}/runs`);
  const users = messages.items.filter((item) => item.role === 'USER');
  const assistants = messages.items.filter((item) => item.role === 'ASSISTANT');
  const taskRuns = runs.items;
  if (users.length !== 1 || assistants.length !== 1 || taskRuns.length !== 1) throw new Error(`Expected one USER Message, one Assistant answer and one Run; got ${users.length}/${assistants.length}/${taskRuns.length}.`);
  const user = users[0];
  const answer = assistants[0];
  const run = taskRuns[0];
  if (user.body !== frozenPrompt || answer.answer_source_message_id !== user.message_id || answer.answer_run_id !== run.run_id || run.source_message_id !== user.message_id || run.status !== 'SUCCEEDED') {
    throw new Error('Initial full question, answer, and formal Run are not correctly linked.');
  }
  if (answer.answer_kind !== 'CHAT_MODEL') throw new Error(`Expected deterministic model-shaped answer, got ${answer.answer_kind}.`);
  if (!answer.body.includes('callback-retry-contract') || !answer.body.includes('HTTP 202') || !answer.body.includes('QUEUED') || !answer.body.includes('未提交')) {
    throw new Error('Deterministic answer does not include the expected sourced QUEUED conclusion and draft boundary.');
  }
  const thread = page.locator(`.conversation-thread[data-source-message-id="${user.message_id}"]`);
  const answerRow = thread.locator(`.message-row.assistant[data-run-id="${run.run_id}"]`);
  await expect(answerRow).toBeVisible();
  const answerTextBeforeReload = await answerRow.innerText();
  const sourceDetails = answerRow.locator('details.followup-sources').first();
  await sourceDetails.locator('summary').click();
  await expect.poll(() => records.some((item) => item.type === 'response' && item.path === `/api/runs/${run.run_id}/assistant-sources` && item.status === 200), { timeout: 15000 }).toBe(true);
  const sourceText = await sourceDetails.innerText();
  const domBeforeReload = await page.locator('body').innerText();
  await page.screenshot({ path: path.join(screenshotDir, 'deterministic-full-flow.png'), fullPage: true });

  const postCountBeforeReload = records.filter((item) => item.type === 'request' && item.method === 'POST').length;
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator(`.conversation-thread[data-source-message-id="${user.message_id}"] .message-row.assistant[data-run-id="${run.run_id}"]`)).toBeVisible();
  const messagesAfter = await api(`/api/sessions/${encodeURIComponent(session.session_id)}/messages`);
  const runsAfter = await api(`/api/sessions/${encodeURIComponent(session.session_id)}/runs`);
  const postCountAfterReload = records.filter((item) => item.type === 'request' && item.method === 'POST').length;
  const bodyAfter = await page.locator(`.conversation-thread[data-source-message-id="${user.message_id}"] .message-row.assistant[data-run-id="${run.run_id}"]`).innerText();
  const sourceDetailsAfter = page.locator(`.conversation-thread[data-source-message-id="${user.message_id}"] .message-row.assistant[data-run-id="${run.run_id}"] details.followup-sources`).first();
  await sourceDetailsAfter.locator('summary').click();
  await expect.poll(() => records.filter((item) => item.type === 'response' && item.path === `/api/runs/${run.run_id}/assistant-sources` && item.status === 200).length, { timeout: 15000 }).toBeGreaterThanOrEqual(2);
  const sourceTextAfterReload = await sourceDetailsAfter.innerText();
  const result = {
    mode: 'fixture',
    evidence_level: 'DETERMINISTIC_FIXTURE_FORMAL_API_WORKER_MCP_DOMAIN_NOT_REAL_PROVIDER_AUTONOMY',
    session_id: session.session_id,
    task_id: run.task_id,
    user_message_id: user.message_id,
    run_id: run.run_id,
    authorized_project_id: visibleProject,
    selected_order_id: selectedOrderId,
    answer_message_id: answer.message_id,
    answer_kind: answer.answer_kind,
    run_status: run.status,
    user_message_count: users.length,
    assistant_answer_count: assistants.length,
    run_count: taskRuns.length,
    answer_text: answer.body,
    answer_same_after_reload: bodyAfter === answerTextBeforeReload,
    refreshed_message_count: messagesAfter.items.length,
    refreshed_run_count: runsAfter.items.length,
    source_detail_text: sourceText,
    source_detail_text_after_reload: sourceTextAfterReload,
    source_details_reloaded: sourceTextAfterReload === sourceText,
    source_endpoint_status_200: records.some((item) => item.type === 'response' && item.path === `/api/runs/${run.run_id}/assistant-sources` && item.status === 200),
    only_one_assistant_order_submission: records.filter((item) => item.type === 'request' && item.method === 'POST' && item.path.endsWith('/assistant/order')).length === 1,
    no_duplicate_assistant_messages_endpoint: records.filter((item) => item.type === 'request' && item.method === 'POST' && item.path.endsWith('/assistant/messages')).length === 0,
    order_submission_post_delta: records.filter((item) => item.type === 'request' && item.method === 'POST').length - initialPosts.length,
    reload_created_no_post: postCountBeforeReload === postCountAfterReload,
    dom_text_before_reload: domBeforeReload,
    api_events: records.slice(),
  };
  if (!result.source_endpoint_status_200 || !result.only_one_assistant_order_submission || !result.no_duplicate_assistant_messages_endpoint || !result.reload_created_no_post) {
    throw new Error('Browser journey produced a duplicate request or failed source/refresh check.');
  }
  await writeFile(path.join(evidenceDir, 'fixture.json'), JSON.stringify(result, null, 2) + '\n', 'utf8');
  await page.screenshot({ path: path.join(screenshotDir, 'deterministic-after-reload.png'), fullPage: true });
}

try {
  if (mode === 'fixture') await runDeterministicFullFlow();
  else if (mode === 'replay-revoked') await inspectRevokedReplay();
  else await inspectSavedReplay();
  console.log(JSON.stringify({ status: 'PASS', mode, browser: 'Microsoft Edge', api_events: records.length }));
} catch (error) {
  try {
    await page.screenshot({ path: path.join(screenshotDir, `${mode}-failure.png`), fullPage: true });
    await writeFile(path.join(evidenceDir, `${mode}-failure.json`), JSON.stringify({
      mode,
      error: String(error),
      body_text: await page.locator('body').innerText().catch(() => ''),
      api_events: records.slice(),
    }, null, 2) + '\n', 'utf8');
  } catch {
    // Preserve the original Playwright failure even if failure capture is unavailable.
  }
  throw error;
} finally {
  await context.close();
  await browser.close();
}
