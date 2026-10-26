import assert from 'node:assert/strict';
import test from 'node:test';
import { projectConversation } from '../src/conversation.ts';

const user = (message_id: string, sequence: number, created_at: string, body = message_id) => ({
  message_id, task_id: 'task-a', sequence, role: 'USER' as const, input_kind: 'CHAT_READONLY',
  body, created_at, application_state: null, applied_run_id: null,
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
