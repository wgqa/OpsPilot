import assert from 'node:assert/strict';
import test from 'node:test';
import { projectConversation } from '../src/conversation.ts';
import { renderAssistantMarkdown } from '../src/markdown.ts';

function makeMessage(overrides) {
  return {
    message_id: 'message-1',
    task_id: null,
    sequence: 1,
    role: 'USER',
    input_kind: 'CHAT_READONLY',
    body: 'Question',
    created_at: '2026-11-10T10:00:00Z',
    application_state: null,
    applied_run_id: null,
    ...overrides,
  };
}

test('assistant messages from one Run render as one turn and retain every source message', () => {
  const user = makeMessage();
  const first = makeMessage({
    message_id: 'answer-1', role: 'ASSISTANT', sequence: 2, body: 'I will compare the contracts.',
    answer_run_id: 'run-1', answer_source_message_id: user.message_id, answer_kind: 'CHAT_MODEL',
  });
  const second = makeMessage({
    message_id: 'answer-2', role: 'ASSISTANT', sequence: 3, body: 'The retry interval changed.',
    answer_run_id: 'run-1', answer_source_message_id: user.message_id, answer_kind: 'CHAT_MODEL',
  });
  const projection = projectConversation({ messages: [user, second, first] });
  const turns = projection.threads[0].items.filter((item) => item.kind === 'CHAT_MESSAGE');

  assert.equal(turns.length, 1);
  assert.deepEqual(turns[0].messages.map((message) => message.message_id), ['answer-1', 'answer-2']);
  assert.equal(turns[0].message.message_id, 'answer-2');
  assert.equal(turns[0].runId, 'run-1');
});

test('different Runs stay separate and mismatched Task messages are not attached to the user turn', () => {
  const user = makeMessage();
  const firstRun = makeMessage({
    message_id: 'answer-1', role: 'ASSISTANT', sequence: 2, answer_run_id: 'run-1',
    answer_source_message_id: user.message_id, answer_kind: 'CHAT_MODEL',
  });
  const secondRun = makeMessage({
    message_id: 'answer-2', role: 'ASSISTANT', sequence: 3, answer_run_id: 'run-2',
    answer_source_message_id: user.message_id, answer_kind: 'CHAT_MODEL',
  });
  const crossTask = makeMessage({
    message_id: 'answer-3', task_id: 'other-task', role: 'ASSISTANT', sequence: 4,
    answer_run_id: 'run-3', answer_source_message_id: user.message_id, answer_kind: 'CHAT_MODEL',
  });
  const projection = projectConversation({ messages: [user, firstRun, secondRun, crossTask] });

  assert.equal(projection.threads[0].items.filter((item) => item.kind === 'CHAT_MESSAGE').length, 2);
  assert.equal(projection.unassociatedItems.some((item) => item.message?.message_id === 'answer-3'), true);
});

test('assistant Markdown renders tables and code while escaping raw HTML and unsafe links', () => {
  const rendered = renderAssistantMarkdown([
    '## Retry settings',
    '',
    '| Field | Value |',
    '| --- | --- |',
    '| attempts | 5 |',
    '',
    '```json',
    '{"backoff":"fixed"}',
    '```',
    '',
    '<script>alert(1)</script> [unsafe](javascript:alert(1)) ![remote](https://example.com/pixel.png)',
  ].join('\n'));

  assert.match(rendered, /<h2>Retry settings<\/h2>/);
  assert.match(rendered, /<table>/);
  assert.match(rendered, /<pre><code class="language-json">/);
  assert.doesNotMatch(rendered, /<script>|href="javascript:|<img\b/);
  assert.match(rendered, /&lt;script&gt;/);
});
