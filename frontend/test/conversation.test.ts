import assert from 'node:assert/strict';
import test from 'node:test';
import { clearS3RestrictedResultCache, createS3ReadResponseFence, filterDeniedS3AssistantMessages, projectConversation, projectSessionEvent, s3InspectorAuthorizationUnavailable,
  type CachedS3Inspector } from '../src/conversation.ts';

const user = (message_id: string, sequence: number, created_at: string, body = message_id) => ({
  message_id, task_id: 'task-a', sequence, role: 'USER' as const, input_kind: 'CHAT_READONLY',
  body, created_at, application_state: null, applied_run_id: null,
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => { resolve = accept; });
  return { promise, resolve };
}

test('same-Task stale authorized Inspector response cannot overwrite later revocation', async () => {
  const fence = createS3ReadResponseFence();
  const taskId = 'task-s3';
  const selectedTaskId = taskId;
  let inspectorResult: Record<string, string> = {
    answer_text: 'restricted S3 answer',
    source_ref: 'restricted source',
    receipt_id: 'restricted receipt',
    evidence_id: 'restricted evidence',
  };
  const oldResponse = deferred<'authorized-old'>();
  const revokedResponse = deferred<'authorization-unavailable'>();

  const applyInspectorResponse = async (
    ticket: ReturnType<typeof fence.beginInspector>,
    response: Promise<'authorized-old' | 'authorization-unavailable'>,
  ) => {
    const result = await response;
    if (!fence.isCurrentInspector(ticket, selectedTaskId)) return;
    if (result === 'authorization-unavailable') {
      if (!fence.denyInspector(ticket)) return;
      inspectorResult = { gate: 'S3_AUTHORIZATION_UNAVAILABLE' };
    } else if (fence.acceptAuthorizedInspector(ticket)) {
      inspectorResult = {
        answer_text: 'restricted S3 answer',
        source_ref: 'restricted source',
        receipt_id: 'restricted receipt',
        evidence_id: 'restricted evidence',
      };
    }
  };

  const requestA = fence.beginInspector(taskId);
  const responseA = applyInspectorResponse(requestA, oldResponse.promise);
  const requestB = fence.beginInspector(taskId);
  const responseB = applyInspectorResponse(requestB, revokedResponse.promise);
  revokedResponse.resolve('authorization-unavailable');
  await responseB;
  oldResponse.resolve('authorized-old');
  await responseA;

  assert.deepEqual(inspectorResult, { gate: 'S3_AUTHORIZATION_UNAVAILABLE' },
    'late authorized response reintroduced the pre-revocation Inspector');
  for (const restricted of ['restricted S3 answer', 'restricted source', 'restricted receipt', 'restricted evidence']) {
    assert.equal(JSON.stringify(inspectorResult).includes(restricted), false);
  }
});

test('keeps legitimate current same-Task refreshes and isolates another Task', () => {
  const fence = createS3ReadResponseFence();
  const firstTaskRequest = fence.beginInspector('task-s3');
  const latestTaskRequest = fence.beginInspector('task-s3');
  const otherTaskRequest = fence.beginInspector('task-other');

  assert.equal(fence.isCurrentInspector(firstTaskRequest, 'task-s3'), false);
  assert.equal(fence.acceptAuthorizedInspector(latestTaskRequest), true);
  assert.equal(fence.isCurrentInspector(otherTaskRequest, 'task-other'), true);
  assert.equal(fence.acceptAuthorizedInspector(otherTaskRequest), true);
});

test('a pre-revocation Session Message response cannot restore a cleared assistant body', async () => {
  const fence = createS3ReadResponseFence();
  const taskId = 'task-s3';
  const sessionId = 'session-1';
  let messages = ['safe user anchor', 'cached restricted assistant body'];
  const oldMessageResponse = deferred<string[]>();
  const messageTicket = fence.beginSessionMessages(sessionId);
  const pendingMessages = oldMessageResponse.promise.then((items) => {
    if (fence.isCurrentSessionMessages(messageTicket, sessionId)) messages = items;
  });

  assert.ok(messages.includes('cached restricted assistant body'));
  const inspectorTicket = fence.beginInspector(taskId);
  assert.ok(fence.denyInspector(inspectorTicket));
  messages = ['safe user anchor'];
  oldMessageResponse.resolve(['safe user anchor', 'restricted S3 assistant body and source']);
  await pendingMessages;

  assert.deepEqual(messages, ['safe user anchor'], 'late Session response restored a restricted assistant body');
});

test('does not clear another Task message and permits a fresh read after authorization returns', () => {
  const fence = createS3ReadResponseFence();
  const deniedTicket = fence.beginInspector('task-s3');
  assert.ok(fence.denyInspector(deniedTicket));
  assert.equal(fence.isTaskDenied('task-s3'), true);

  const filtered = filterDeniedS3AssistantMessages([
    { ...user('s3-user', 1, '2026-01-01T00:00:00Z'), task_id: 'task-s3' },
    { ...user('s3-answer', 2, '2026-01-01T00:00:01Z', 's3 answer'), role: 'ASSISTANT' as const,
      task_id: 'task-s3' },
    { ...user('other-answer', 3, '2026-01-01T00:00:02Z', 'other task answer'), role: 'ASSISTANT' as const,
      task_id: 'task-other' },
  ], (taskId) => taskId === 'task-s3' && fence.isTaskDenied(taskId));
  assert.deepEqual(filtered.map((message) => message.message_id), ['s3-user', 'other-answer']);

  const reauthorizedTicket = fence.beginInspector('task-s3');
  assert.equal(fence.acceptAuthorizedInspector(reauthorizedTicket), true);
  assert.equal(fence.isTaskDenied('task-s3'), false);
  assert.deepEqual(filterDeniedS3AssistantMessages([
    { ...user('s3-answer', 1, '2026-01-01T00:00:00Z', 'fresh authorized answer'), role: 'ASSISTANT' as const,
      task_id: 'task-s3' },
  ], (taskId) => fence.isTaskDenied(taskId)).map((message) => message.message_id), ['s3-answer']);

  const staleBeforeRevocation = fence.beginSessionMessages('session-1');
  const nextInspectorTicket = fence.beginInspector('task-s3');
  const nextDeniedTicket = fence.denyInspector(nextInspectorTicket);
  assert.ok(nextDeniedTicket);
  assert.equal(fence.isCurrentSessionMessages(staleBeforeRevocation, 'session-1'), false);
  const reauthorizedAgain = fence.beginInspector('task-s3');
  assert.equal(fence.acceptAuthorizedInspector(reauthorizedAgain), true);
  const freshMessages = fence.beginSessionMessages('session-1');
  assert.equal(fence.isCurrentSessionMessages(freshMessages, 'session-1'), true);
});

test('groups interleaved results under exact source messages and keeps late answer timestamps', () => {
  const projection = projectConversation({
    messages: [
      user('q1', 1, '2026-01-01T00:00:00Z', 'first question'),
      user('q2', 2, '2026-01-01T00:01:00Z', 'second question'),
      { ...user('a2', 3, '2026-01-01T00:02:00Z', 'second answer'), role: 'ASSISTANT' as const,
        answer_run_id: 'chat-r2', answer_source_message_id: 'q2', answer_kind: 'CHAT_MODEL' as const },
      user('q3', 4, '2026-01-01T00:03:00Z', 'third question'),
    ],
    runs: [
      { run_id: 'investigate-r1', source_message_id: 'q1', task_id: 'task-a', kind: 'INVESTIGATE',
        status: 'SUCCEEDED', created_at: '2026-01-01T00:00:01Z', ended_at: '2026-01-01T00:01:30Z' },
    ],
    investigationAnswers: [
      { run_id: 'investigate-r1', source_message_id: 'q1', answer_text: 'late first answer',
        result_state: 'ANSWERED', created_at: '2026-01-01T00:04:00Z', source_refs: [] },
    ],
  });

  assert.deepEqual(projection.threads.map((thread) => thread.anchor.message_id), ['q1', 'q2', 'q3']);
  assert.deepEqual(projection.threads[0]?.items.map((item) => item.id), ['investigation:investigate-r1']);
  assert.equal(projection.threads[0]?.items.at(-1)?.createdAt, '2026-01-01T00:04:00Z');
  assert.deepEqual(projection.threads[1]?.items.map((item) => item.id), ['message:a2']);
  assert.equal(projection.threads[1]?.items[0]?.message?.body, 'second answer');
});

test('does not guess a missing source, preserves same-text operations, and filters routed chat failures', () => {
  const projection = projectConversation({
    messages: [
      user('q1', 1, '2026-01-01T00:00:00Z', 'same text'),
      user('q2', 2, '2026-01-01T00:01:00Z', 'same text'),
      { ...user('orphan', 3, '2026-01-01T00:02:00Z', 'unlinked reply'), role: 'ASSISTANT' as const },
    ],
    runs: [
      { run_id: 'chat-blocked', source_message_id: 'q1', task_id: 'task-a', kind: 'CHAT_READONLY',
        status: 'BLOCKED', blocked_reason: 'FOLLOWUP_ROUTED_TO_INVESTIGATOR', created_at: '2026-01-01T00:00:01Z' },
      { run_id: 'business-failed', source_message_id: 'q2', task_id: 'task-a', kind: 'INVESTIGATE',
        status: 'FAILED', blocked_reason: 'MODEL_BUDGET_EXHAUSTED', created_at: '2026-01-01T00:01:01Z' },
    ],
  });

  assert.deepEqual(projection.threads[0]?.items, []);
  assert.equal(projection.threads[1]?.items[0]?.id, 'run:business-failed');
  assert.equal(projection.threads[1]?.items[0]?.kind, 'RUN_STATUS');
  assert.deepEqual(projection.unassociatedItems.map((item) => item.message?.message_id), ['orphan']);
});

test('links a confirmed correction and its new run under the exact originating message once', () => {
  const correction = {
    ...user('correction-clone', 3, '2026-01-01T00:02:00Z', 'the callback was reconfigured'),
    input_kind: 'CORRECT_TASK_INPUT', application_state: 'APPLIED_TO_RUN', applied_run_id: 'new-run',
  };
  const projection = projectConversation({
    messages: [user('q1', 1, '2026-01-01T00:00:00Z'), user('q2', 2, '2026-01-01T00:01:00Z'), correction],
    runs: [{ run_id: 'new-run', source_message_id: 'correction-clone', task_id: 'task-a', kind: 'INVESTIGATE',
      status: 'RUNNING', created_at: '2026-01-01T00:03:00Z' }],
    assessments: [{ assessment_id: 'assessment-1', source_message_id: 'q2', task_id: 'task-a',
      intent: 'CRITICAL_CORRECTION', status: 'CONFIRMED', correction_message_id: 'correction-clone',
      investigation_run_id: 'new-run', change_summary: 'updated fact' }],
  });

  assert.deepEqual(projection.threads.map((thread) => thread.anchor.message_id), ['q1', 'q2']);
  assert.deepEqual(projection.threads[1]?.items.map((item) => item.id), ['assessment:assessment-1', 'run:new-run']);
  assert.equal(projection.threads[1]?.items[0]?.correctionMessage?.message_id, 'correction-clone');
});

test('deduplicates replayed stable ids and renders only the active source run chunks', () => {
  const anchor = user('q1', 1, '2026-01-01T00:00:00Z');
  const projection = projectConversation({
    messages: [anchor, anchor],
    activeChatRun: { run_id: 'chat-r1', task_id: 'task-a', source_message_id: 'q1', kind: 'CHAT_READONLY',
      status: 'RUNNING', created_at: '2026-01-01T00:00:01Z' },
    chunks: [
      { chunk_id: 'chunk-1', chunk_seq: 1, body: 'hello', body_digest: 'd1', created_at: '2026-01-01T00:00:02Z', attempt_id: 'attempt-1' },
      { chunk_id: 'chunk-1', chunk_seq: 1, body: 'hello', body_digest: 'd1', created_at: '2026-01-01T00:00:02Z', attempt_id: 'attempt-1' },
      { chunk_id: 'chunk-2', chunk_seq: 2, body: ' world', body_digest: 'd2', created_at: '2026-01-01T00:00:03Z', attempt_id: 'attempt-1' },
    ],
  });

  assert.equal(projection.threads.length, 1);
  assert.deepEqual(projection.threads[0]?.items.map((item) => item.id), ['stream:chat-r1']);
  assert.deepEqual(projection.threads[0]?.items[0]?.chunks?.map((chunk) => chunk.body), ['hello', ' world']);
});

test('keeps waiting and failed outcomes visible without duplicating an ordinary Follow-up card', () => {
  const projection = projectConversation({
    messages: [
      user('classifying-question', 1, '2026-01-01T00:00:00Z'),
      user('confirm-question', 2, '2026-01-01T00:01:00Z'),
      user('followup-question', 3, '2026-01-01T00:02:00Z'),
      user('partial-question', 4, '2026-01-01T00:03:00Z'),
      user('limit-question', 5, '2026-01-01T00:04:00Z'),
      user('failed-question', 6, '2026-01-01T00:05:00Z'),
      { ...user('limit-answer', 7, '2026-01-01T00:04:30Z', '额度已用尽，尚未完成当前状态核实。'),
        role: 'ASSISTANT' as const, answer_run_id: 'limit-run',
        answer_source_message_id: 'limit-question', answer_kind: 'PROGRAM_LIMIT' as const },
    ],
    runs: [
      { run_id: 'classification-sidecar', source_message_id: 'classifying-question', task_id: 'task-a',
        kind: 'CHAT_READONLY', status: 'BLOCKED', blocked_reason: 'UPDATE_CLASSIFICATION_PENDING', created_at: '2026-01-01T00:00:01Z' },
      { run_id: 'confirmation-sidecar', source_message_id: 'confirm-question', task_id: 'task-a',
        kind: 'CHAT_READONLY', status: 'BLOCKED', blocked_reason: 'UPDATE_CONFIRMATION_PENDING', created_at: '2026-01-01T00:01:01Z' },
      { run_id: 'routed-sidecar', source_message_id: 'followup-question', task_id: 'task-a',
        kind: 'CHAT_READONLY', status: 'BLOCKED', blocked_reason: 'FOLLOWUP_ROUTED_TO_INVESTIGATOR', created_at: '2026-01-01T00:02:01Z' },
      { run_id: 'followup-run', source_message_id: 'followup-question', task_id: 'task-a',
        kind: 'INVESTIGATE', status: 'SUCCEEDED', created_at: '2026-01-01T00:02:02Z' },
      { run_id: 'failed-run', source_message_id: 'failed-question', task_id: 'task-a',
        kind: 'INVESTIGATE', status: 'FAILED', blocked_reason: 'MCP_TIMEOUT', created_at: '2026-01-01T00:05:01Z' },
      { run_id: 'partial-run', source_message_id: 'partial-question', task_id: 'task-a',
        kind: 'INVESTIGATE', status: 'SUCCEEDED', created_at: '2026-01-01T00:03:01Z' },
      { run_id: 'limit-run', source_message_id: 'limit-question', task_id: 'task-a',
        kind: 'CHAT_READONLY', status: 'BLOCKED', blocked_reason: 'TASK_MODEL_LIMIT', created_at: '2026-01-01T00:04:01Z' },
    ],
    assessments: [
      { assessment_id: 'classification-wait', source_message_id: 'classifying-question', task_id: 'task-a',
        intent: 'UNKNOWN', status: 'ASSESSING' },
      { assessment_id: 'confirmation-wait', source_message_id: 'confirm-question', task_id: 'task-a',
        intent: 'CRITICAL_CORRECTION', status: 'PENDING_CONFIRMATION',
        proposal: { status: 'PENDING_CONFIRMATION' } },
      { assessment_id: 'ordinary-followup', source_message_id: 'followup-question', task_id: 'task-a',
        intent: 'FOLLOW_UP', follow_up_action: 'INVESTIGATE', status: 'NO_UPDATE' },
    ],
    readonlyFollowups: [{ run_id: 'followup-run', source_message_id: 'followup-question', expected_control_revision: 0,
      result_state: 'ANSWERED', answer_text: '同一 Task 的合法补查答复。', source_refs: [], result: {},
      created_at: '2026-01-01T00:02:02Z', completed_at: '2026-01-01T00:02:03Z', run_status: 'SUCCEEDED' }],
    investigationAnswers: [{ run_id: 'partial-run', source_message_id: 'partial-question',
      answer_text: '已确认投递受理，接收方处理状态仍未知。', result_state: 'PARTIAL', source_refs: [],
      created_at: '2026-01-01T00:03:02Z' }],
  });

  const itemIds = (messageId: string) => projection.threads
    .find((thread) => thread.anchor.message_id === messageId)?.items.map((item) => item.id) ?? [];
  assert.deepEqual(itemIds('classifying-question'), ['assessment:classification-wait']);
  assert.deepEqual(itemIds('confirm-question'), ['assessment:confirmation-wait']);
  assert.deepEqual(itemIds('followup-question'), ['followup:followup-run']);
  assert.deepEqual(itemIds('partial-question'), ['investigation:partial-run']);
  assert.deepEqual(itemIds('limit-question'), ['message:limit-answer']);
  assert.deepEqual(itemIds('failed-question'), ['run:failed-run']);
  assert.equal(projection.threads.find((thread) => thread.anchor.message_id === 'limit-question')
    ?.items[0]?.message?.answer_kind, 'PROGRAM_LIMIT');
});

test('clears revoked S3 result caches without removing unrelated conversation messages', () => {
  const priorAnswer = { run_id: 'initial-run', source_message_id: 's3-question',
    answer_text: 'restricted initial S3 answer', result_state: 'ANSWERED', source_refs: [], result: {},
    created_at: '2026-01-01T00:00:01Z', report_ref: 'restricted-receipt' };
  const priorFollowup = { run_id: 'followup-run', source_message_id: 's3-followup-question',
    expected_control_revision: 0, result_state: 'ANSWERED', answer_text: 'restricted C1 Follow-up answer',
    source_refs: [{ evidence_id: 'restricted-evidence' }], result: { private_detail: 'restricted-result' },
    created_at: '2026-01-01T00:01:01Z', run_status: 'SUCCEEDED' };
  const inspector: CachedS3Inspector = {
    task: { task_id: 'task-s3', service_id: 'orders-async-demo' },
    trusted_state: { s3_outcome: { receipt_id: 'restricted-receipt', outcome: 'RECEIVER_PROCESSED' },
      s3_handoff: { receipt_id: 'restricted-handoff' } },
    current_gate: { decision: 'DIAGNOSED', checked_fact_ids: ['restricted-evidence'] },
    runs: [
      { run_id: 'initial-run', task_id: 'task-s3', source_message_id: 's3-question', kind: 'INVESTIGATE',
        status: 'SUCCEEDED', created_at: '2026-01-01T00:00:00Z' },
      { run_id: 'followup-run', task_id: 'task-s3', source_message_id: 's3-followup-question', kind: 'INVESTIGATE',
        status: 'SUCCEEDED', created_at: '2026-01-01T00:01:00Z' },
    ],
    evidence: [{ evidence_id: 'restricted-evidence' }],
    observations: [{ evidence_id: 'restricted-evidence' }],
    investigation_answers: [priorAnswer],
    readonly_followups: [priorFollowup],
    task_input_messages: [{ message_id: 's3-question' }],
    investigation_model_traces: [{ evidence_id: 'restricted-evidence' }],
    chat_model_attempts: [],
    chat_context_provenance: [{ evidence_refs: ['restricted-evidence'] }],
    investigator_context_provenance: [{ evidence_ids: ['restricted-evidence'] }],
  };
  const messages = [
    { ...user('s3-question', 1, '2026-01-01T00:00:00Z'), task_id: 'task-s3' },
    { ...user('s3-followup-question', 2, '2026-01-01T00:01:00Z'), task_id: 'task-s3' },
    { ...user('s3-answer', 3, '2026-01-01T00:02:00Z', 'restricted S3 chat response'),
      task_id: 'task-s3', role: 'ASSISTANT' as const, answer_run_id: 'initial-run',
      answer_source_message_id: 's3-question', answer_kind: 'CHAT_MODEL' as const },
    { ...user('orphan-s3-answer', 4, '2026-01-01T00:02:01Z', 'restricted orphan response'),
      task_id: null, role: 'ASSISTANT' as const, answer_run_id: 'followup-run',
      answer_source_message_id: 's3-followup-question', answer_kind: 'CHAT_MODEL' as const },
    { ...user('other-question', 5, '2026-01-01T00:03:00Z'), task_id: 'task-other' },
    { ...user('other-answer', 6, '2026-01-01T00:04:00Z', 'unrelated response'),
      task_id: 'task-other', role: 'ASSISTANT' as const, answer_run_id: 'other-run',
      answer_source_message_id: 'other-question', answer_kind: 'CHAT_MODEL' as const },
  ];

  assert.equal(s3InspectorAuthorizationUnavailable(inspector), false);
  const revoked = { ...inspector, trusted_state: { ...inspector.trusted_state,
    s3_outcome: { currentness: 'INVALIDATED_BY_CURRENT_FACTS',
      gate: { reason_code: 'S3_AUTHORIZATION_UNAVAILABLE' } } } };
  assert.equal(s3InspectorAuthorizationUnavailable(revoked), true);
  assert.equal(s3InspectorAuthorizationUnavailable({ ...revoked, trusted_state: { ...revoked.trusted_state,
    s3_outcome: { currentness: 'INVALIDATED_BY_CURRENT_FACTS', gate: { reason_code: 'S3_SLA_EXPIRED' } } } }), false);

  const cleared = clearS3RestrictedResultCache(revoked, messages, 'task-s3');
  assert.deepEqual(cleared.inspector?.investigation_answers, []);
  assert.deepEqual(cleared.inspector?.readonly_followups, []);
  assert.deepEqual(cleared.inspector?.evidence, []);
  assert.deepEqual(cleared.inspector?.observations, []);
  assert.deepEqual(cleared.inspector?.investigator_context_provenance, []);
  assert.deepEqual(cleared.messages.map((message) => message.message_id), ['s3-question', 's3-followup-question', 'other-question', 'other-answer']);
  const projection = projectConversation({
    messages: cleared.messages,
    runs: cleared.inspector?.runs,
    investigationAnswers: cleared.inspector?.investigation_answers,
    readonlyFollowups: cleared.inspector?.readonly_followups,
  });
  const rendered = JSON.stringify(projection);
  for (const restricted of ['restricted initial S3 answer', 'restricted C1 Follow-up answer',
    'restricted S3 chat response', 'restricted orphan response', 'restricted-receipt', 'restricted-evidence']) {
    assert.equal(rendered.includes(restricted), false, `stale result reached projection: ${restricted}`);
  }
  assert.deepEqual(projection.unassociatedItems, []);
});

test('does not project restricted bodies or receipts from a previously received SSE event', () => {
  const event = projectSessionEvent({
    event_seq: 88,
    event_kind: 'S3_HANDOFF_ACCEPTED',
    happened_at: '2026-01-01T00:00:00Z',
    payload: { answer_text: 'restricted S3 body', receipt_id: 'restricted-receipt', source_refs: ['restricted-evidence'] },
  });
  assert.deepEqual(event, {
    event_seq: 88,
    event_kind: 'S3_HANDOFF_ACCEPTED',
    happened_at: '2026-01-01T00:00:00Z',
  });
  for (const restricted of ['restricted S3 body', 'restricted-receipt', 'restricted-evidence']) {
    assert.equal(JSON.stringify(event).includes(restricted), false);
  }
});
