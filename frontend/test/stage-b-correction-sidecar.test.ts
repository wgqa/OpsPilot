import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { projectConversation } from '../src/conversation.ts';
import type { Inspector, MessageItem } from '../src/api.ts';

interface Snapshot {
  inspector: Inspector;
  messages: { items: MessageItem[] };
  assessments: { items: Array<Record<string, unknown> & {
    assessment_id: string;
    source_message_id: string;
    target_task_id: string;
    intent: string;
    status: string;
    correction_message_id?: string;
    investigation_run_id?: string;
  }> };
}

interface ApiPayload { confirmed: Snapshot; ids: Record<string, string> }

function apiSnapshot(): ApiPayload {
  const path = new URL('../../docs/evidence/vnext/m4-cont-ux-01/stage-b/closeout-01/runs/green-api-05/responses/correction-answered.json', import.meta.url);
  return JSON.parse(readFileSync(path, 'utf8')) as ApiPayload;
}

function user(id: string, sequence: number, taskId = 'task-s3', inputKind = 'CHAT_READONLY'): MessageItem {
  return { message_id: id, task_id: taskId, sequence, role: 'USER', input_kind: inputKind,
    body: id, created_at: `2026-01-01T00:00:0${sequence}Z`, application_state: null, applied_run_id: null };
}

test('real API correction takeover sidecar is not a second unfinished user result', () => {
  const payload = apiSnapshot();
  const snapshot = payload.confirmed;
  const sidecar = snapshot.inspector.runs.find((run) => run.kind === 'CHAT_READONLY'
    && run.status === 'BLOCKED' && run.blocked_reason === 'CORRECTION_CONFIRMED');
  assert.ok(sidecar, 'saved authenticated API JSON must contain the reported sidecar');
  assert.equal(sidecar.source_message_id, payload.ids.question);

  const projection = projectConversation({
    messages: snapshot.messages.items,
    runs: snapshot.inspector.runs,
    investigationAnswers: snapshot.inspector.investigation_answers,
    readonlyFollowups: snapshot.inspector.readonly_followups,
    assessments: snapshot.assessments.items,
    s3Outcome: snapshot.inspector.trusted_state.s3_outcome as Record<string, unknown> | null,
  });
  const thread = projection.threads.find((item) => item.anchor.message_id === payload.ids.question);
  assert.ok(thread);
  assert.equal(thread.items.some((item) => item.id === `run:${sidecar.run_id}`), false,
    'CORRECTION_CONFIRMED Chat sidecar must not render as unfinished work');

  const details = thread.items.find((item) => item.kind === 'CORRECTION_ASSESSMENT');
  assert.ok(details?.supersededChatRuns?.some((run) => run.run_id === sidecar.run_id
    && run.status === 'BLOCKED' && run.blocked_reason === 'CORRECTION_CONFIRMED'),
  'original sidecar Run must remain available in expandable correction details');
  assert.ok(thread.items.some((item) => item.id === `investigation:${payload.ids.run}`),
    'the completed investigation result must remain visible');
});

test('suppresses only correction takeover sidecars and keeps genuine investigation failures visible', () => {
  const question = user('question', 1);
  const correction = { ...user('correction', 2, 'task-s3', 'CORRECT_TASK_INPUT'),
    application_state: 'APPLIED_TO_RUN', applied_run_id: 'new-investigation' };
  const failedQuestion = user('failed-question', 3);
  const sidecar = { run_id: 'correction-chat-sidecar', task_id: 'task-s3', source_message_id: question.message_id,
    kind: 'CHAT_READONLY', status: 'BLOCKED', blocked_reason: 'CORRECTION_CONFIRMED', created_at: '2026-01-01T00:00:01Z' };
  const investigation = { run_id: 'new-investigation', task_id: 'task-s3', source_message_id: correction.message_id,
    kind: 'INVESTIGATE', status: 'SUCCEEDED', created_at: '2026-01-01T00:00:02Z' };
  const failed = { run_id: 'genuine-failure', task_id: 'task-s3', source_message_id: failedQuestion.message_id,
    kind: 'INVESTIGATE', status: 'FAILED', blocked_reason: 'MCP_TIMEOUT', created_at: '2026-01-01T00:00:03Z' };
  const projection = projectConversation({
    messages: [question, correction, failedQuestion],
    runs: [sidecar, investigation, failed],
    assessments: [{ assessment_id: 'confirmed-correction', source_message_id: question.message_id,
      target_task_id: 'task-s3', intent: 'CRITICAL_CORRECTION', status: 'CONFIRMED',
      correction_message_id: correction.message_id, investigation_run_id: investigation.run_id }],
  });
  const questionThread = projection.threads.find((item) => item.anchor.message_id === question.message_id);
  assert.ok(questionThread);
  assert.equal(questionThread.items.some((item) => item.id === `run:${sidecar.run_id}`), false);
  assert.ok(questionThread.items.find((item) => item.kind === 'CORRECTION_ASSESSMENT')
    ?.supersededChatRuns?.some((run) => run.run_id === sidecar.run_id));
  const failureThread = projection.threads.find((item) => item.anchor.message_id === failedQuestion.message_id);
  assert.equal(failureThread?.items.find((item) => item.id === `run:${failed.run_id}`)?.run?.blocked_reason, 'MCP_TIMEOUT');
});
