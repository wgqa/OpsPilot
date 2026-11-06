import assert from 'node:assert/strict';
import test from 'node:test';
import { acknowledgeAssistantOperation, beginAssistantOperation, controlledInvestigationProposal, recentAssistantSourceRequests, type OperationStore } from '../src/assistant-entry.ts';
import { api } from '../src/api.ts';
import { projectConversation } from '../src/conversation.ts';

function store(): OperationStore {
  const values = new Map<string, string>();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value); },
    removeItem: (key) => { values.delete(key); },
  };
}

test('controlled-investigation CTA requires a current proposal tied to the exact original user message', () => {
  const result = {
    success: true,
    proposal_type: 'CONTROLLED_AUTH_INVESTIGATION',
    authority: 'MODEL_SUGGESTION_ONLY_UNTRUSTED',
    rationale: '需要检查可信资源范围。',
    source_message_id: 'message-original',
    task_created: false,
    authorization_created: false,
    requires_explicit_user_confirmation: true,
  };
  const sources = {
    current: true,
    items: [{ tool_name: 'propose_controlled_auth_investigation', status: 'OK', result }],
  };
  assert.deepEqual(controlledInvestigationProposal(sources, 'message-original'), {
    rationale: '需要检查可信资源范围。', sourceMessageId: 'message-original',
  });
  assert.equal(controlledInvestigationProposal(sources, 'adjacent-message'), null);
  assert.equal(controlledInvestigationProposal({ ...sources, current: false }, 'message-original'), null);
  assert.equal(controlledInvestigationProposal({
    current: true,
    items: [{ tool_name: 'propose_controlled_auth_investigation', status: 'OK', result: { ...result, task_created: true } }],
  }, 'message-original'), null);
});

test('restored Assistant sources use exact persisted question links and a small bounded recent set', () => {
  const items = [
    { role: 'USER' as const, message_id: 'u1', task_id: null, answer_run_id: null, answer_source_message_id: null, answer_kind: null },
    { role: 'ASSISTANT' as const, message_id: 'a1', task_id: null, answer_run_id: 'run-1', answer_source_message_id: 'u1', answer_kind: 'CHAT_MODEL' as const },
    { role: 'USER' as const, message_id: 'u2', task_id: null, answer_run_id: null, answer_source_message_id: null, answer_kind: null },
    { role: 'ASSISTANT' as const, message_id: 'a2', task_id: null, answer_run_id: 'run-2', answer_source_message_id: 'u2', answer_kind: 'CHAT_MODEL' as const },
    { role: 'ASSISTANT' as const, message_id: 'program', task_id: null, answer_run_id: 'run-program', answer_source_message_id: 'u2', answer_kind: 'PROGRAM_LIMIT' as const },
    { role: 'ASSISTANT' as const, message_id: 'wrong-link', task_id: null, answer_run_id: 'run-wrong', answer_source_message_id: 'absent-user', answer_kind: 'CHAT_MODEL' as const },
  ];
  assert.deepEqual(recentAssistantSourceRequests(items, 1), [
    { runId: 'run-2', sourceMessageId: 'u2', taskId: null },
  ]);
  assert.deepEqual(recentAssistantSourceRequests(items, 8), [
    { runId: 'run-2', sourceMessageId: 'u2', taskId: null },
    { runId: 'run-1', sourceMessageId: 'u1', taskId: null },
  ]);
});

test('unknown HTTP result reuses operation after reconstruction without storing pasted text', async () => {
  const storage = store();
  const payload = { body: 'sensitive pasted log', task_id: null };
  const first = await beginAssistantOperation(storage, 'actor/session/message', payload, () => 'operation-1');
  const retry = await beginAssistantOperation(storage, 'actor/session/message', payload, () => 'must-not-create');
  assert.equal(retry.operationId, first.operationId);
  assert.equal(retry.requestDigest.length, 64);
  assert.equal(storage.getItem('actor/session/message')?.includes('sensitive pasted log'), false);
});

test('accepted identical text is a new user operation; distinct Session and changed target stay distinct', async () => {
  const storage = store();
  const payload = { body: 'same text', task_id: null };
  const first = await beginAssistantOperation(storage, 'a/s1', payload, () => 'one');
  acknowledgeAssistantOperation(storage, 'a/s1', first.operationId);
  assert.equal((await beginAssistantOperation(storage, 'a/s1', payload, () => 'two')).operationId, 'two');
  assert.equal((await beginAssistantOperation(storage, 'a/s2', payload, () => 'three')).operationId, 'three');
  assert.equal((await beginAssistantOperation(storage, 'a/s1', { ...payload, task_id: 'authorized-task' }, () => 'four')).operationId, 'four');
});

test('late acknowledgement cannot discard a newer pending operation', async () => {
  const storage = store();
  await beginAssistantOperation(storage, 'a/s1', { body: 'old' }, () => 'old');
  await beginAssistantOperation(storage, 'a/s1', { body: 'new' }, () => 'new');
  acknowledgeAssistantOperation(storage, 'a/s1', 'old');
  assert.equal(JSON.parse(storage.getItem('a/s1') ?? '{}').operationId, 'new');
});

test('malformed storage never becomes a trusted request identity', async () => {
  const storage = store();
  storage.setItem('a/s1', '{broken');
  assert.equal((await beginAssistantOperation(storage, 'a/s1', { body: 'question' }, () => 'fresh')).operationId, 'fresh');
});

test('professional API uses caller operation and trusted selection endpoints, not a classification sidecar', async () => {
  const previousFetch = globalThis.fetch;
  const calls: Array<{ path: string; init: RequestInit }> = [];
  globalThis.fetch = async (input, init = {}) => {
    calls.push({ path: String(input), init });
    return new Response(JSON.stringify({ run_id: 'run-1', message_id: 'message-1' }), { status: 202 });
  };
  try {
    await api.assistantSend('session/one', 'concept', null, 'csrf-local', 'explicit-message-operation');
    await api.bindAssistantOrder('session/one', 'authorized-order', 'check this order', 'csrf-local', 'explicit-order-operation');
    await api.assistantScopes('session/one');
    await api.selectAssistantScope('session/one', 'authorized-project', 'csrf-local');
    assert.deepEqual(calls.map((call) => call.path), [
      '/api/sessions/session%2Fone/assistant/messages',
      '/api/sessions/session%2Fone/assistant/order',
      '/api/sessions/session%2Fone/assistant/scopes',
      '/api/sessions/session%2Fone/assistant/scopes',
    ]);
    assert.deepEqual(JSON.parse(String(calls[0].init.body)), { body: 'concept', task_id: null });
    assert.equal(new Headers(calls[0].init.headers).get('Idempotency-Key'), 'explicit-message-operation');
    assert.deepEqual(JSON.parse(String(calls[1].init.body)), { order_id: 'authorized-order', initial_message: 'check this order' });
    assert.equal(new Headers(calls[1].init.headers).get('Idempotency-Key'), 'explicit-order-operation');
    assert.equal(calls[2].init.credentials, 'same-origin');
    assert.equal(calls[3].init.method, 'PUT');
    assert.deepEqual(JSON.parse(String(calls[3].init.body)), { project_id: 'authorized-project' });
    assert.equal(calls.some((call) => call.path.includes('investigation-updates')), false);
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test('same Session no-Task answer and later bound answer stay under exact original questions', () => {
  const messages = [
    { message_id: 'concept', task_id: null, sequence: 1, role: 'USER' as const, input_kind: 'CHAT_READONLY', body: 'What does 202 mean?', created_at: '2026-10-30T01:00:00Z', application_state: null, applied_run_id: null },
    { message_id: 'order', task_id: 'bound-task', sequence: 2, role: 'USER' as const, input_kind: 'CHAT_READONLY', body: 'Check authorized order', created_at: '2026-10-30T01:01:00Z', application_state: null, applied_run_id: null },
    { message_id: 'concept-answer', task_id: null, sequence: 3, role: 'ASSISTANT' as const, input_kind: 'CHAT_READONLY', body: '202 is acceptance.', created_at: '2026-10-30T01:02:00Z', application_state: null, applied_run_id: null, answer_source_message_id: 'concept', answer_run_id: 'run-concept', answer_kind: 'CHAT_MODEL' as const },
    { message_id: 'order-answer', task_id: 'bound-task', sequence: 4, role: 'ASSISTANT' as const, input_kind: 'CHAT_READONLY', body: 'Current receipt still unknown.', created_at: '2026-10-30T01:03:00Z', application_state: null, applied_run_id: null, answer_source_message_id: 'order', answer_run_id: 'run-order', answer_kind: 'CHAT_MODEL' as const },
  ];
  const projection = projectConversation({ messages });
  assert.equal(projection.threads[0].anchor.message_id, 'concept');
  assert.deepEqual(projection.threads[0].items.filter((item) => item.kind === 'CHAT_MESSAGE').map((item) => item.message?.message_id), ['concept-answer']);
  assert.equal(projection.threads[1].anchor.message_id, 'order');
  assert.deepEqual(projection.threads[1].items.filter((item) => item.kind === 'CHAT_MESSAGE').map((item) => item.message?.message_id), ['order-answer']);
  assert.equal(projection.unassociatedItems.length, 0);
});
