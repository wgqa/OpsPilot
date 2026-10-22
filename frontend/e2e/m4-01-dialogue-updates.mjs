import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium, expect } from '@playwright/test';

const baseURL = process.env.OPSPILOT_M4_UI_URL;
const supportPassword = process.env.OPSPILOT_M4_SUPPORT_PASSWORD;
const screenshotDir = process.env.OPSPILOT_M4_SCREENSHOTS;
const scenario = process.env.OPSPILOT_M4_SCENARIO ?? 'S1_401';
const mode = process.env.OPSPILOT_M4_MODE ?? 'journey';
const targetTaskId = process.env.OPSPILOT_M4_TASK_ID;
const targetSessionId = process.env.OPSPILOT_M4_SESSION_ID;
const resultPath = process.env.OPSPILOT_M4_RESULT_PATH;
if (!baseURL || !supportPassword || !screenshotDir || !resultPath) {
  throw new Error('M4-01 browser acceptance configuration is incomplete.');
}

await mkdir(screenshotDir, { recursive: true });
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const network = [];
page.on('response', (response) => {
  const url = new URL(response.url());
  if (url.pathname.startsWith('/api/')) {
    network.push({ method: response.request().method(), path: url.pathname, status: response.status() });
  }
});

async function login() {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await page.getByLabel('演示身份').selectOption('support-a');
  await page.getByLabel('本地口令').fill(supportPassword);
  await page.getByRole('button', { name: '登录工作台' }).click();
  await expect(page.locator('.rail-footer')).toBeVisible({ timeout: 20000 });
  const response = network.find((item) => item.method === 'POST' && item.path === '/api/auth/login');
  if (!response || response.status !== 200) throw new Error('Isolated support-a browser login did not return HTTP 200.');
}

async function apiJson(url) {
  return page.evaluate(async (target) => {
    const response = await fetch(target);
    return { status: response.status, body: await response.json() };
  }, url);
}

async function inspector(taskId) {
  const response = await apiJson(`/api/tasks/${encodeURIComponent(taskId)}/inspector`);
  if (response.status !== 200) throw new Error(`Task inspector returned ${response.status}.`);
  return response.body;
}

async function sessionRuns(sessionId) {
  const response = await apiJson(`/api/sessions/${encodeURIComponent(sessionId)}/runs`);
  if (response.status !== 200) throw new Error(`Session Runs returned ${response.status}.`);
  return response.body.items;
}

async function waitRun(runId) {
  await expect.poll(async () => {
    const response = await apiJson(`/api/runs/${encodeURIComponent(runId)}`);
    return response.status === 200 ? response.body.status : `HTTP_${response.status}`;
  }, { timeout: 300000, intervals: [500, 1000, 2000] })
    .not.toMatch(/^(QUEUED|RUNNING|INTERRUPTED_RECOVERABLE)$/);
  const response = await apiJson(`/api/runs/${encodeURIComponent(runId)}`);
  if (response.status !== 200) throw new Error(`Run lookup returned ${response.status}.`);
  if (['FAILED', 'BLOCKED'].includes(response.body.status)) {
    throw new Error(`Investigation Run failed: ${response.body.status} ${response.body.waiting_reason ?? ''}`);
  }
  return response.body;
}

async function startTask(initialMessage) {
  await page.getByRole('button', { name: '新建调查任务' }).first().click();
  await page.getByTestId('initial-symptom-input').fill(initialMessage);
  const acceptedPromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/tasks'));
  await page.getByRole('button', { name: '启动调查' }).click();
  const acceptedResponse = await acceptedPromise;
  if (acceptedResponse.status() !== 202) throw new Error(`Task create returned ${acceptedResponse.status()}.`);
  const accepted = await acceptedResponse.json();
  await waitRun(accepted.run_id);
  await expect.poll(async () => page.locator('.task-summary-card').getAttribute('data-task-id'),
    { timeout: 30000, intervals: [100, 250, 500] }).toBe(accepted.task_id);
  return accepted;
}

async function sendChat(taskId, body, priorAssistantCount) {
  await page.getByTestId('message-input').fill(body);
  const acceptedPromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/messages'));
  await page.getByRole('button', { name: '发送消息' }).click();
  const acceptedResponse = await acceptedPromise;
  if (acceptedResponse.status() !== 202) throw new Error(`CHAT_READONLY submit returned ${acceptedResponse.status()}.`);
  const accepted = await acceptedResponse.json();
  await expect.poll(async () => page.locator('.message-row.assistant').count(),
    { timeout: 180000, intervals: [250, 500, 1000] }).toBe(priorAssistantCount + 1);
  await expect.poll(async () => {
    const response = await apiJson(`/api/tasks/${encodeURIComponent(taskId)}/investigation-updates`);
    return response.status === 200
      ? response.body.items.some((item) => item.source_message_id === accepted.message_id && item.status !== 'ASSESSING')
      : false;
  }, { timeout: 90000, intervals: [250, 500, 1000] }).toBe(true);
  return accepted;
}

async function assessmentFor(taskId, messageId) {
  const response = await apiJson(`/api/tasks/${encodeURIComponent(taskId)}/investigation-updates`);
  if (response.status !== 200) throw new Error(`Assessment history returned ${response.status}.`);
  const item = response.body.items.find((candidate) => candidate.source_message_id === messageId);
  if (!item) throw new Error(`No persisted classifier result for source message ${messageId}.`);
  return item;
}

function checkedEvidence(inspectorData) {
  const checked = new Set(Array.isArray(inspectorData.current_gate?.checked_fact_ids)
    ? inspectorData.current_gate.checked_fact_ids : []);
  return inspectorData.evidence.filter((item) => checked.has(item.evidence_id));
}

function factsWithStatus(inspectorData, status) {
  return checkedEvidence(inspectorData).filter((item) => item.facts?.http_status === status);
}

async function resumeAfterServiceRestart() {
  await login();
  const history = await apiJson(`/api/tasks/${encodeURIComponent(targetTaskId)}/investigation-updates`);
  const task = await inspector(targetTaskId);
  const messages = await apiJson(`/api/sessions/${encodeURIComponent(targetSessionId)}/messages`);
  if (history.status !== 200 || messages.status !== 200) throw new Error('Persisted browser state is not readable after API restart.');
  const confirmed = history.body.items.find((item) => item.status === 'CONFIRMED');
  if (!confirmed || !confirmed.investigation_run_id || !confirmed.correction_message_id) {
    throw new Error('Confirmed proposal, correction message, or re-investigation Run was lost after API restart.');
  }
  const confirmedRun = task.runs.find((item) => item.run_id === confirmed.investigation_run_id);
  if (!confirmedRun || ['QUEUED', 'RUNNING'].includes(confirmedRun.status)) {
    throw new Error('Confirmed Task Run did not recover to a durable terminal/waiting state after API restart.');
  }
  await page.screenshot({ path: path.join(screenshotDir, '05-after-api-restart.png'), fullPage: true });
  return {
    mode: 'resume', scenario, task_id: targetTaskId, session_id: targetSessionId,
    assessment_id: confirmed.assessment_id, correction_message_id: confirmed.correction_message_id,
    investigation_run_id: confirmed.investigation_run_id, run_status: confirmedRun.status,
    current_gate: task.current_gate, current_evidence_count: task.evidence.length,
    persisted_message_count: messages.body.items.length, api_status: 200,
  };
}

async function runJourney() {
  await login();
  await page.locator('.new-session-button').click();
  const initialMessage = 'orders-demo 的订单 API 最近返回 401，请核实当前绑定路由的真实响应和原因。';
  const created = await startTask(initialMessage);
  const taskId = String(created.task_id);
  const sessionId = String(created.session_id);
  if (!sessionId) throw new Error('Created task did not return its persisted Session ID.');
  const initialRun = await waitRun(created.run_id);
  const initialInspector = await inspector(taskId);
  const initialBusinessRuns = (await sessionRuns(sessionId)).filter((item) => item.kind !== 'CHAT_READONLY').length;
  const initialRevision = initialInspector.trusted_state.control_revision;
  const initialPlanHash = initialInspector.trusted_state.plan?.plan_hash ?? null;
  const expectedStatus = scenario === 'S1_401' ? 401 : 403;
  if (factsWithStatus(initialInspector, expectedStatus).length === 0) {
    throw new Error(`Initial current Gate does not include the expected current HTTP ${expectedStatus} Probe.`);
  }
  await page.screenshot({ path: path.join(screenshotDir, '01-initial-investigation.png'), fullPage: true });

  let assistantCount = await page.locator('.message-row.assistant').count();
  let followup = null;
  let followupAssessment = null;
  let hypothesis = null;
  let hypothesisAssessment = null;
  if (scenario === 'S1_401') {
    followup = await sendChat(taskId, '为什么这个 Task 当前仍判定为鉴权失败？请解释现有证据。', assistantCount);
    assistantCount += 1;
    followupAssessment = await assessmentFor(taskId, followup.message_id);
    if (followupAssessment.intent !== 'FOLLOW_UP' || followupAssessment.proposal !== null) {
      throw new Error(`A normal question was not kept explanation-only: ${followupAssessment.intent}.`);
    }
    const afterFollowup = await inspector(taskId);
    const afterFollowupBusinessRuns = (await sessionRuns(sessionId)).filter((item) => item.kind !== 'CHAT_READONLY').length;
    if (afterFollowup.trusted_state.control_revision !== initialRevision
        || afterFollowupBusinessRuns !== initialBusinessRuns) {
      throw new Error('Ordinary follow-up changed TaskControl revision or created a business Run.');
    }

    hypothesis = await sendChat(taskId, '假设主体其实被禁用会发生什么？我不确定，这只是讨论，不要改 Task。', assistantCount);
    assistantCount += 1;
    hypothesisAssessment = await assessmentFor(taskId, hypothesis.message_id);
    if (hypothesisAssessment.intent !== 'HYPOTHESIS' || hypothesisAssessment.proposal !== null) {
      throw new Error(`A speculative message produced a formal correction proposal: ${hypothesisAssessment.intent}.`);
    }
    const afterHypothesis = await inspector(taskId);
    const afterHypothesisBusinessRuns = (await sessionRuns(sessionId)).filter((item) => item.kind !== 'CHAT_READONLY').length;
    if (afterHypothesis.trusted_state.control_revision !== initialRevision
        || afterHypothesisBusinessRuns !== initialBusinessRuns) {
      throw new Error('Hypothesis discussion changed TaskControl revision or created a business Run.');
    }
  }

  const correctionText = scenario === 'S1_401'
    ? '正式更正：现场日志确认这次订单请求是 403；我之前写成 401 是旧信息。请把这条明确线索纳入 Task 输入并重新核对当前真实请求，最终以新 Probe 为准。'
    : '正式更正：现场日志确认当前这次订单请求是 403；我之前写成 401 是旧监控。请基于当前 Task 绑定路由重新调查对应的授权事实。';
  const correction = await sendChat(taskId, correctionText, assistantCount);
  const assessment = await assessmentFor(taskId, correction.message_id);
  if (assessment.intent !== 'CRITICAL_CORRECTION' || !assessment.proposal
      || assessment.proposal.source_message_id !== correction.message_id
      || assessment.proposal.target_task_id !== taskId
      || assessment.proposal.expected_control_revision !== initialRevision) {
    throw new Error(`Explicit correction did not produce a versioned same-Task proposal: ${assessment.intent}.`);
  }
  await expect(page.getByTestId(`investigation-update-${assessment.assessment_id}`)).toBeVisible({ timeout: 15000 });
  await page.screenshot({ path: path.join(screenshotDir, '02-reviewable-correction-proposal.png'), fullPage: true });
  const proposal = assessment.proposal;
  const confirmationResponsePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST'
      && new URL(response.url()).pathname.endsWith(`/investigation-updates/${proposal.proposal_id}/confirm`));
  await page.getByTestId(`investigation-update-${assessment.assessment_id}`)
    .getByRole('button', { name: '确认并重新调查' }).click();
  const confirmationResponse = await confirmationResponsePromise;
  if (confirmationResponse.status() !== 200) {
    throw new Error(`Explicitly confirmed proposal returned ${confirmationResponse.status()}.`);
  }
  const confirmed = await confirmationResponse.json();
  const correctedRun = await waitRun(confirmed.run_id);
  const correctedInspector = await inspector(taskId);
  const correctedAssessment = (await apiJson(`/api/tasks/${encodeURIComponent(taskId)}/investigation-updates`))
    .body.items.find((item) => item.assessment_id === assessment.assessment_id);
  const correctedInput = correctedInspector.task_input_messages.find((item) => item.message_id === confirmed.message_id);
  const correctedContext = correctedInspector.investigator_context_provenance.find((item) =>
    item.task_run_control?.run_id === confirmed.run_id);
  const correctedRunRecord = correctedInspector.runs.find((item) => item.run_id === confirmed.run_id);
  const retiredPlan = initialPlanHash
    ? correctedInspector.plan_history.find((item) => item.plan_hash === initialPlanHash)
    : null;
  if (correctedAssessment?.status !== 'CONFIRMED'
      || correctedAssessment.correction_message_id !== confirmed.message_id
      || correctedAssessment.investigation_run_id !== confirmed.run_id
      || confirmed.expected_control_revision !== initialRevision + 1
      || correctedInput?.accepted_control_revision !== initialRevision + 1
      || correctedInput?.applied_control_revision !== initialRevision + 2
      || correctedRunRecord?.expected_control_revision !== initialRevision + 2
      || correctedInspector.trusted_state.control_revision !== initialRevision + 2
      || correctedInput?.application_state !== 'APPLIED_TO_RUN'
      || correctedInput?.applied_run_id !== confirmed.run_id
      || !correctedContext?.selected_input_messages?.some((item) => item.message_id === confirmed.message_id)
      || (initialPlanHash !== null && (!retiredPlan || retiredPlan.eligibility === 'ACTIVE'))) {
    throw new Error('Confirmed correction was not applied atomically to the new Investigator Run.');
  }
  const actualFacts = factsWithStatus(correctedInspector, expectedStatus);
  if (actualFacts.length === 0) {
    throw new Error(`The post-correction deterministic Gate did not use the real HTTP ${expectedStatus} fact.`);
  }
  if (scenario === 'S1_401' && correctedInspector.current_gate.decision !== 'READY') {
    throw new Error(`The unchanged real 401 fact was not judged by the existing S1 Gate: ${correctedInspector.current_gate.decision}.`);
  }
  if (scenario === 'S2_403') {
    const outcome = correctedInspector.s2_outcome;
    const receipt = outcome?.diagnosis_receipt;
    const receiptEvidenceIds = new Set(receipt?.evidence_ids ?? []);
    const gateEvidenceIds = new Set(correctedInspector.current_gate.checked_fact_ids ?? []);
    const predicate = receipt?.predicate ?? {};
    if (!receipt?.request_id || !receipt?.decision_id || receiptEvidenceIds.size !== 2
        || [...receiptEvidenceIds].some((evidenceId) => !gateEvidenceIds.has(evidenceId))
        || predicate.request_id !== receipt.request_id
        || predicate.decision_id !== receipt.decision_id
        || predicate.authz_outcome !== 'DENY'
        || predicate.reason_code !== 'SCOPE_INSUFFICIENT'
        || !['DIAGNOSED', 'HANDOFF_READY'].includes(outcome?.business_outcome)) {
      throw new Error('The current 403 Probe is not correlated with trusted Domain Authz Decision evidence.');
    }
  }
  const businessRunsAfter = (await sessionRuns(sessionId)).filter((item) => item.kind !== 'CHAT_READONLY');
  if (businessRunsAfter.length !== initialBusinessRuns + 1) {
    throw new Error(`Expected exactly one new Investigator Run, observed ${businessRunsAfter.length - initialBusinessRuns}.`);
  }
  const statusNotice = page.locator('[role="status"]').last();
  await expect(statusNotice).toContainText('重新调查已结束', { timeout: 30000 });
  await expect(statusNotice).toContainText(`Probe HTTP ${expectedStatus}`);
  const notice = await statusNotice.innerText();
  await page.screenshot({ path: path.join(screenshotDir, '03-confirmed-and-reinvestigated.png'), fullPage: true });
  await page.reload({ waitUntil: 'domcontentloaded' });
  const reloadHistory = await apiJson(`/api/tasks/${encodeURIComponent(taskId)}/investigation-updates`);
  const reloadInspector = await inspector(taskId);
  if (reloadHistory.status !== 200
      || !reloadHistory.body.items.some((item) => item.assessment_id === assessment.assessment_id && item.status === 'CONFIRMED')
      || reloadInspector.trusted_state.control_revision !== initialRevision + 2) {
    throw new Error('Page refresh lost the confirmed correction or TaskControl revision.');
  }
  await page.screenshot({ path: path.join(screenshotDir, '04-after-page-refresh.png'), fullPage: true });
  return {
    mode: 'journey', scenario, task_id: taskId, session_id: sessionId,
    initial: {
      message_id: created.message_id, run_id: created.run_id, run_status: initialRun.status,
      control_revision: initialRevision, plan_hash: initialPlanHash,
      gate: initialInspector.current_gate,
      current_probe_statuses: [...new Set(checkedEvidence(initialInspector).map((item) => item.facts?.http_status).filter(Boolean))],
    },
    ordinary_followup: {
      message_id: followup?.message_id ?? null, intent: followupAssessment?.intent ?? null,
      proposal: followupAssessment?.proposal ?? null,
      task_control_revision_unchanged: followupAssessment !== null,
      business_run_count_unchanged: followupAssessment !== null,
      provider_response_id: followupAssessment?.model_attempt?.provider_response_id ?? null,
      total_tokens: followupAssessment?.model_attempt?.total_tokens ?? null,
    },
    hypothesis: {
      message_id: hypothesis?.message_id ?? null, intent: hypothesisAssessment?.intent ?? null,
      proposal: hypothesisAssessment?.proposal ?? null,
      task_control_revision_unchanged: hypothesisAssessment !== null,
      business_run_count_unchanged: hypothesisAssessment !== null,
      provider_response_id: hypothesisAssessment?.model_attempt?.provider_response_id ?? null,
      total_tokens: hypothesisAssessment?.model_attempt?.total_tokens ?? null,
    },
    correction: {
      source_message_id: correction.message_id, intent: assessment.intent, assessment_id: assessment.assessment_id,
      proposal_id: proposal.proposal_id, operation_id: proposal.operation_id,
      expected_control_revision: proposal.expected_control_revision,
      correction_message_id: confirmed.message_id, investigation_run_id: confirmed.run_id,
      investigation_run_status: correctedRun.status, new_control_revision: correctedInspector.trusted_state.control_revision,
      confirmation_admission_revision: confirmed.expected_control_revision,
      correction_application_revision: correctedRunRecord?.expected_control_revision,
      retired_plan: retiredPlan,
      current_gate: correctedInspector.current_gate,
      current_valid_evidence: correctedInspector.evidence,
      matching_probe_facts: actualFacts.map((item) => ({ evidence_id: item.evidence_id, fact_type: item.fact_type, facts: item.facts })),
      task_input_application: correctedInput,
      investigator_context: correctedContext,
      s2_outcome: correctedInspector.s2_outcome ?? null,
      classifier_provider_response_id: assessment.model_attempt?.provider_response_id ?? null,
      classifier_tokens: assessment.model_attempt?.total_tokens ?? null,
      confirmation_revision_increased_once: confirmed.expected_control_revision === initialRevision + 1,
      application_revision_recorded_by_existing_task_control: correctedInspector.trusted_state.control_revision === initialRevision + 2,
      exactly_one_new_investigator_run: businessRunsAfter.length === initialBusinessRuns + 1,
      chat_action_counts: correctedInspector.trusted_state.action_counts,
      ui_notice: notice,
    },
    http: network,
  };
}

let result;
try {
  if (mode === 'resume') result = await resumeAfterServiceRestart();
  else result = await runJourney();
  const scrub = (value) => {
    if (Array.isArray(value)) return value.map(scrub);
    if (value && typeof value === 'object') {
      return Object.fromEntries(Object.entries(value).map(([key, item]) =>
        [/api[_-]?key|password|secret|authorization|cookie/i.test(key) ? '[REDACTED]' : key, scrub(item)]));
    }
    return value;
  };
  const safeResult = scrub(result);
  await writeFile(resultPath, `${JSON.stringify(safeResult, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify(safeResult));
} finally {
  await context.close();
  await browser.close();
}
