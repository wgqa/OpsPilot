import assert from 'node:assert/strict';
import test from 'node:test';
import type { MessageItem } from '../src/api.ts';
import * as conversation from '../src/conversation.ts';

const answer: MessageItem = {
  message_id: 'answer-s3', task_id: 'task-s3', sequence: 501, role: 'ASSISTANT',
  input_kind: 'CHAT_READONLY', body: 'Authorized S3 result', created_at: '2026-11-12T02:00:00Z',
  application_state: null, applied_run_id: null, answer_kind: 'CHAT_MODEL',
  answer_run_id: 'run-s3', answer_source_message_id: 'question-s3', answer_visibility: 'HISTORICAL_SNAPSHOT',
};

test('reconnect masks loaded S3 snapshots before the server revalidates the visible page', () => {
  const user = { ...answer, role: 'USER' as const, sequence: 500, body: 'My question' };
  const ordinary = { ...answer, task_id: null, answer_visibility: undefined, body: 'Ordinary answer' };
  const masked = conversation.maskS3AnswersForRevalidation([user, answer, ordinary]);
  assert.deepEqual(masked.map(item => item.sequence), [500, 501, 501]);
  assert.equal(masked[1].answer_visibility, 'HIDDEN');
  assert.ok(!JSON.stringify(masked).includes(answer.body));
  assert.equal(masked[0], user);
  assert.equal(masked[2], ordinary);
});

test('a denied or switched session cannot reapply an older authorized snapshot response', () => {
  const fence = conversation.createS3ReadResponseFence();
  const current = fence.beginSessionMessages('session-a');
  let cache = conversation.maskS3AnswersForRevalidation([answer]);
  const inspector = fence.beginInspector('task-s3');
  fence.denyInspector(inspector);
  if (fence.isCurrentSessionMessages(current, 'session-a')) cache = [answer];
  assert.ok(!JSON.stringify(cache).includes(answer.body));

  const recheck = fence.beginSessionMessages('session-a');
  fence.beginSessionMessages('session-b');
  assert.equal(fence.isCurrentSessionMessages(recheck, 'session-b'), false);
  assert.equal(fence.isCurrentSessionMessages(recheck, 'session-a'), false);
  const currentResponse = fence.beginSessionMessages('session-a');
  assert.equal(fence.isCurrentSessionMessages(currentResponse, 'session-a'), true);
  assert.deepEqual(conversation.filterDeniedS3AssistantMessages([answer], fence.isTaskDenied), []);
});
