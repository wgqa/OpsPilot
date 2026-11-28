import assert from 'node:assert/strict';
import test from 'node:test';
import { api } from '../src/api.ts';
import { acknowledgeAssistantOperation, beginAssistantOperation } from '../src/assistant-entry.ts';
import { assistantTaskForSend, s1OutcomeText } from '../src/s1-bridge.ts';
import { projectConversation } from '../src/conversation.ts';
import { readFileSync } from 'node:fs';

test('task creation sends the stable caller operation and explicit original message', async () => {
  const prior = globalThis.fetch;
  let request: RequestInit | undefined;
  globalThis.fetch = async (_input, init = {}) => {
    request = init;
    return new Response(JSON.stringify({ task_id: 'task-1', run_id: 'run-1' }), { status: 202 });
  };
  try {
    await api.createTask('session-1', '401 after rotation', 'csrf', 'AUTH_INCIDENT', undefined, 'operation-1', 'message-original');
    assert.equal(new Headers(request?.headers).get('Idempotency-Key'), 'operation-1');
    assert.deepEqual(JSON.parse(String(request?.body)), {
      initial_message: '401 after rotation', investigation_kind: 'AUTH_INCIDENT', source_message_id: 'message-original',
    });
  } finally {
    globalThis.fetch = prior;
  }
});

test('lost response keeps operation identity; accepted new intent receives another identity', async () => {
  const entries = new Map<string, string>();
  const store = { getItem: (key: string) => entries.get(key) ?? null,
    setItem: (key: string, value: string) => { entries.set(key, value); },
    removeItem: (key: string) => { entries.delete(key); } };
  const payload = { initial_message: '401', source_message_id: 'source-1', investigation_kind: 'AUTH_INCIDENT' };
  const first = await beginAssistantOperation(store, 'actor/session/s1-task', payload, () => 'first');
  const retry = await beginAssistantOperation(store, 'actor/session/s1-task', payload, () => 'unexpected');
  assert.equal(retry.operationId, first.operationId);
  assert.equal(entries.get('actor/session/s1-task')?.includes('401'), false);
  acknowledgeAssistantOperation(store, 'actor/session/s1-task', first.operationId);
  assert.equal((await beginAssistantOperation(store, 'actor/session/s1-task', payload, () => 'second')).operationId, 'second');
});

test('Assistant never binds an S1 task to the S3-only task message path', () => {
  assert.equal(assistantTaskForSend('s1', { task_id: 's1', service_id: 'orders-demo' }), null);
  assert.equal(assistantTaskForSend('s3', { task_id: 's3', service_id: 'orders-async-demo' }), 's3');
  assert.equal(assistantTaskForSend('s3', { task_id: 'other', service_id: 'orders-async-demo' }), null);
  assert.equal(assistantTaskForSend('s3', null), null);
});

test('Run success and unverified approval cannot claim recovery; trusted rejection and verification are distinct', () => {
  const base = { task_id: 't', task_status: 'CREATED', business_outcome: 'NO_PLAN' };
  assert.match(s1OutcomeText(base, 'CREATED', 'SUCCEEDED'), /尚未确认业务恢复/);
  assert.match(s1OutcomeText(base, 'WAITING_APPROVAL', 'SUCCEEDED'), /无法与可信方案核对/);
  assert.match(s1OutcomeText({ ...base, business_outcome: 'WAITING_APPROVAL', plan: { plan_hash: 'p', eligibility: 'ACTIVE' } }, 'WAITING_APPROVAL', 'WAITING_APPROVAL'), /等待独立审批；尚未修复/);
  assert.match(s1OutcomeText({ ...base, business_outcome: 'WAITING_APPROVAL', plan: { plan_hash: 'p', eligibility: 'EXPIRED' } }, 'WAITING_APPROVAL', 'WAITING_APPROVAL'), /无法与可信方案核对/);
  assert.match(s1OutcomeText({ ...base, business_outcome: 'REJECTED' }, 'REJECTED', 'SUCCEEDED'), /审批已拒绝/);
  assert.match(s1OutcomeText({ ...base, business_outcome: 'REPAIR_COMMITTED' }, 'VERIFYING', 'SUCCEEDED'), /配置变更已提交；在线业务恢复尚未验证/);
  assert.match(s1OutcomeText({ ...base, business_outcome: 'REAPPROVAL_REQUIRED' }, 'WAITING_APPROVAL', 'WAITING_APPROVAL'), /已形成新方案并等待独立审批/);
  assert.match(s1OutcomeText({ ...base, business_outcome: 'REVALIDATION_BLOCKED' }, 'WAITING_INPUT', 'WAITING_INPUT'), /没有执行修复/);
  assert.match(s1OutcomeText({ ...base, business_outcome: 'UNKNOWN' }, 'WAITING_INPUT', 'WAITING_INPUT'), /无法确认审批后的当前事实/);
  assert.doesNotMatch(s1OutcomeText({ ...base, business_outcome: 'DELIVERED' }, 'SUCCEEDED', 'SUCCEEDED'), /已通过在线业务验证/);
  assert.match(s1OutcomeText({ ...base, business_outcome: 'DELIVERED', verification: { recovery_verified: true } }, 'SUCCEEDED', 'SUCCEEDED'), /已通过在线业务验证/);
  assert.match(s1OutcomeText(base, 'EXPIRED', 'FAILED'), /未能完成或已失效/);
});

test('actual persisted API messages and Inspector runs project the S1 run under its confirmed message',
  { skip: !process.env.AR05_TRACE_PATH }, () => {
    const trace = JSON.parse(readFileSync(process.env.AR05_TRACE_PATH!, 'utf8'));
    const projection = projectConversation({ messages: trace.messages, runs: trace.inspector_runs });
    const initial = projection.threads.find((thread) => thread.anchor.message_id === trace.initial_message_id);
    const original = projection.threads.find((thread) => thread.anchor.message_id === trace.origin_message_id);
    assert.ok(original && initial);
    assert.equal(initial.anchor.investigation_origin_message_id, original.anchor.message_id);
    assert.equal(initial.anchor.task_id, trace.task_id);
    assert.ok(initial.items.some((item) => item.runId === trace.run_id && item.kind === 'RUN_STATUS'));
    assert.equal(trace.run.execution_core, 'PROFESSIONAL_INVESTIGATOR');
    assert.equal(trace.outcome.business_outcome, 'WAITING_APPROVAL');
  });
