import assert from 'node:assert/strict';
import test from 'node:test';
import { createS3ReadResponseFence, projectConversation,
  type ConversationAnswer, type ConversationAssessment, type ConversationRun } from '../src/conversation.ts';
import type { MessageItem } from '../src/api.ts';

function message(id: string, sequence: number, taskId = 'task-s3'): MessageItem {
  return { message_id: id, task_id: taskId, sequence, role: 'USER', input_kind: 'CHAT_READONLY',
    body: id, created_at: `2026-01-01T00:00:0${sequence}Z`, application_state: null, applied_run_id: null };
}

function confirmedCorrection(state: 'ANSWERED' | 'PARTIAL') {
  const question = message('correction-question', 1);
  const correction: MessageItem = { ...message('correction-message', 2), input_kind: 'CORRECT_TASK_INPUT',
    application_state: 'APPLIED_TO_RUN', applied_run_id: 'corrected-run' };
  const run: ConversationRun = { run_id: 'corrected-run', task_id: 'task-s3', source_message_id: correction.message_id,
    kind: 'INVESTIGATE', status: 'SUCCEEDED', created_at: '2026-01-01T00:00:03Z' };
  const answer: ConversationAnswer = { run_id: run.run_id, source_message_id: correction.message_id,
    answer_text: '新的调查结论与未知事项', result_state: state, source_refs: [], created_at: '2026-01-01T00:00:04Z',
    report_ref: 'current-receipt' };
  const assessment: ConversationAssessment = { assessment_id: 'assessment', source_message_id: question.message_id,
    target_task_id: 'task-s3', intent: 'CRITICAL_CORRECTION', status: 'CONFIRMED',
    correction_message_id: correction.message_id, investigation_run_id: run.run_id };
  const diagnosis = { receipt_id: 'current-receipt', currentness: 'CURRENT', outcome: 'RECEIVER_PROCESSED',
    body: { task_id: 'task-s3', run_id: run.run_id } };
  return { messages: [question, correction], runs: [run], investigationAnswers: [answer],
    assessments: [assessment], s3Outcome: diagnosis };
}

test('confirmed applied correction anchors ANSWERED and PARTIAL results with their matching diagnosis', () => {
  for (const state of ['ANSWERED', 'PARTIAL'] as const) {
    const fixture = confirmedCorrection(state);
    const projection = projectConversation(fixture);
    const thread = projection.threads.find((item) => item.anchor.message_id === 'correction-question');
    const result = thread?.items.find((item) => item.kind === 'INVESTIGATION_ANSWER');
    assert.equal(result?.answer?.result_state, state);
    assert.equal(result?.answer?.source_message_id, 'correction-message');
    assert.equal(result?.runId, 'corrected-run');
    assert.equal(result?.diagnosis?.receipt_id, 'current-receipt');
    assert.equal(projection.threads.some((item) => item.anchor.message_id === 'correction-message'), false);
  }
});

test('only confirmed and applied same-Task corrections remap a Run; stale diagnosis never follows it', () => {
  for (const status of ['PENDING_CONFIRMATION', 'CANCELLED', 'STALE']) {
    const fixture = confirmedCorrection('ANSWERED');
    fixture.assessments[0]!.status = status;
    fixture.investigationAnswers = [];
    const thread = projectConversation(fixture).threads.find((item) => item.anchor.message_id === 'correction-question');
    assert.equal(thread?.items.some((item) => item.runId === 'corrected-run'), false, status);
  }
  for (const invalidation of ['not-applied', 'wrong-applied-run', 'wrong-task'] as const) {
    const fixture = confirmedCorrection('ANSWERED');
    if (invalidation === 'not-applied') fixture.messages[1]!.application_state = 'RECEIVED_NOT_APPLIED';
    if (invalidation === 'wrong-applied-run') fixture.messages[1]!.applied_run_id = 'other-run';
    if (invalidation === 'wrong-task') fixture.assessments[0]!.target_task_id = 'other-task';
    fixture.investigationAnswers = [];
    const thread = projectConversation(fixture).threads.find((item) => item.anchor.message_id === 'correction-question');
    assert.equal(thread?.items.some((item) => item.runId === 'corrected-run'), false, invalidation);
  }
  for (const mismatch of ['receipt', 'run', 'task', 'currentness'] as const) {
    const fixture = confirmedCorrection('ANSWERED');
    if (mismatch === 'receipt') fixture.s3Outcome.receipt_id = 'old-receipt';
    if (mismatch === 'run') fixture.s3Outcome.body.run_id = 'old-run';
    if (mismatch === 'task') fixture.s3Outcome.body.task_id = 'other-task';
    if (mismatch === 'currentness') fixture.s3Outcome.currentness = 'UNKNOWN';
    const thread = projectConversation(fixture).threads.find((item) => item.anchor.message_id === 'correction-question');
    const result = thread?.items.find((item) => item.kind === 'INVESTIGATION_ANSWER');
    assert.ok(result, mismatch);
    assert.equal(result.diagnosis, undefined, mismatch);
  }
});

test('confirmed applied correction uses the same source mapping for followup and streaming results', () => {
  const fixture = confirmedCorrection('ANSWERED');
  const run = { ...fixture.runs[0]!, status: 'RUNNING' };
  const followup = { run_id: run.run_id, source_message_id: 'correction-message', expected_control_revision: 1,
    result_state: 'PARTIAL', answer_text: '仍需核实接收状态', source_refs: [], result: {},
    created_at: '2026-01-01T00:00:04Z', run_status: 'SUCCEEDED' };
  const projection = projectConversation({ ...fixture, runs: [run], investigationAnswers: [], readonlyFollowups: [followup] });
  const thread = projection.threads.find((item) => item.anchor.message_id === 'correction-question');
  assert.equal(thread?.items.some((item) => item.kind === 'READONLY_FOLLOWUP'), true);
  const streaming = projectConversation({ ...fixture, runs: [run], investigationAnswers: [], s3Outcome: null,
    activeChatRun: run, chunks: [{ chunk_id: 'chunk-1', chunk_seq: 1, body: '正在核实', body_digest: 'digest',
      created_at: '2026-01-01T00:00:05Z', attempt_id: 'attempt-1' }] });
  assert.equal(streaming.threads.find((item) => item.anchor.message_id === 'correction-question')
    ?.items.some((item) => item.kind === 'STREAM'), true);
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => { resolve = accept; });
  return { promise, resolve };
}

test('normal authorized Inspector refresh preserves a parallel later Session message response', async () => {
  const fence = createS3ReadResponseFence();
  const messages = deferred<string[]>();
  const messageTicket = fence.beginSessionMessages('session');
  const inspectorTicket = fence.beginInspector('task-s3');
  let displayed: string[] = [];
  const pending = messages.promise.then((items) => {
    if (fence.isCurrentSessionMessages(messageTicket, 'session')) displayed = items;
  });
  assert.equal(fence.acceptAuthorizedInspector(inspectorTicket), true);
  messages.resolve(['new legitimate message']);
  await pending;
  assert.deepEqual(displayed, ['new legitimate message']);
});
