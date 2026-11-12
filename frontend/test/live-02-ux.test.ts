import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { parse } from 'vue/compiler-sfc';
import type { ChatChunk, MessageItem, RunActivity } from '../src/api.ts';
import { projectConversation, type ConversationRun } from '../src/conversation.ts';
import { renderAssistantMarkdown } from '../src/markdown.ts';

const created_at = '2026-11-12T02:00:00Z';
const question: MessageItem = {
  message_id: 'question', sequence: 1, role: 'USER', input_kind: 'CHAT_READONLY',
  task_id: 'task-s3', body: 'Query the bound order', created_at, application_state: null, applied_run_id: null,
};
const run: ConversationRun = {
  run_id: 'run-s3', source_message_id: question.message_id, task_id: question.task_id,
  kind: 'CHAT_READONLY', status: 'RUNNING', execution_core: 'ASSISTANT_V1', created_at,
};
const activity = (event_seq: number, stage: string, run_id = run.run_id): RunActivity => ({
  event_seq, event_kind: 'ASSISTANT_ACTIVITY', happened_at: created_at,
  payload: { run_id, stage, activity_status: 'STARTED' },
});
const chunk = (chunk_seq: number, body: string): ChatChunk => ({
  chunk_id: `chunk-${chunk_seq}`, chunk_seq, body, body_digest: 'fixture', created_at, attempt_id: 'attempt',
});

test('waiting and tool activity belong to the same live reply before the first Provider delta', () => {
  const activities = [activity(3, 'TOOL_RUNNING'), activity(1, 'MODEL_REQUESTING'),
    activity(3, 'TOOL_RUNNING'), activity(4, 'SAVING_ANSWER', 'another-run')];
  const thread = projectConversation({ messages: [question], activeChatRun: run, activities }).threads[0];
  assert.deepEqual(thread.items.map(item => item.kind), ['STREAM']);
  assert.equal(thread.items[0].id, `stream:${run.run_id}`);
  assert.deepEqual(thread.items[0].chunks, []);
  assert.deepEqual(thread.items[0].activities?.map(item => item.payload.stage), ['MODEL_REQUESTING', 'TOOL_RUNNING']);

  const streaming = projectConversation({ messages: [question], activeChatRun: run, activities,
    chunks: [chunk(2, ' world'), chunk(1, 'Hello'), chunk(1, 'Hello')] }).threads[0].items;
  assert.equal(streaming[0].id, thread.items[0].id);
  assert.equal(streaming[0].chunks?.map(item => item.body).join(''), 'Hello world');
});

test('a committed answer replaces its draft and shows only authorized same-run activity', () => {
  const final: MessageItem = {
    ...question, message_id: 'answer', sequence: 2, role: 'ASSISTANT', body: 'Complete answer',
    answer_run_id: run.run_id, answer_source_message_id: question.message_id, answer_kind: 'CHAT_MODEL',
    answer_visibility: 'CURRENT',
  };
  const activeChatRun = { ...run, status: 'SUCCEEDED' };
  const activities = [activity(1, 'MODEL_STREAMING'), activity(2, 'SAVING_ANSWER')];
  const project = (message: MessageItem) => projectConversation({ messages: [question, message],
    activeChatRun, activities, chunks: [chunk(1, 'draft')] }).threads[0].items;
  assert.deepEqual(project(final).map(item => item.kind), ['CHAT_MESSAGE']);
  assert.equal(project(final)[0].activities?.at(-1)?.payload.stage, 'SAVING_ANSWER');
  assert.equal(project({ ...final, answer_visibility: 'HIDDEN', body: 'Hidden' })[0].activities, undefined);
  assert.equal(project({ ...final, answer_visibility: 'HISTORICAL_SNAPSHOT' })[0].activities, undefined);
});

test('assistant Markdown renders focusable code with escaped markup and no remote images', () => {
  const html = renderAssistantMarkdown('## SQL\n\n```sql\nselect "<script>";\n```\n\n![remote](https://example.invalid/pixel)\n\n[unsafe](javascript:alert(1))');
  assert.match(html, /<h2>SQL<\/h2>/);
  assert.match(html, /<pre tabindex="0" aria-label="代码块"><code class="language-sql">/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script|<img|href="javascript:/);
});

test('one personal memory form is mounted in the one Inspector across viewport layouts', () => {
  const source = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8');
  const { descriptor, errors } = parse(source);
  assert.deepEqual(errors, []);
  const nodes = descriptor.template?.ast.children ?? [];
  assert.ok(nodes.length > 0);
  assert.equal((descriptor.template?.content.match(/data-testid="personal-memory-proposal"/g) ?? []).length, 1);
  assert.equal((descriptor.template?.content.match(/class="inspector-panel panel"/g) ?? []).length, 1);
  const styles = readFileSync(new URL('../src/style.css', import.meta.url), 'utf8');
  const openLayouts = [...styles.matchAll(/\.inspector-panel\.open\s*\{([^}]+)\}/g)].map(match => match[1]);
  assert.ok(openLayouts.some(style => /position:\s*absolute/.test(style)));
  assert.ok(!openLayouts.some(style => /position:\s*fixed/.test(style)));
});
