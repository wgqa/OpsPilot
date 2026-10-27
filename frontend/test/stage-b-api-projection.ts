import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { projectConversation, type ConversationAssessment } from '../src/conversation.ts';
import type { Inspector, MessageItem } from '../src/api.ts';

// This driver consumes unmodified JSON returned by the authenticated test API.
interface Snapshot {
  inspector: Inspector;
  messages: { items: MessageItem[] };
  assessments?: { items: ConversationAssessment[] };
}
interface Payload { authorized: Snapshot; revoked: Snapshot; confirmed: Snapshot; chat?: Snapshot;
  ids: Record<string, string>; restricted: string[] }
const data = JSON.parse(readFileSync(process.argv[2]!, 'utf8')) as Payload;
const mode = process.argv[3];
const project = (snapshot: Snapshot) => projectConversation({
  messages: snapshot.messages.items,
  runs: snapshot.inspector.runs,
  investigationAnswers: snapshot.inspector.investigation_answers,
  readonlyFollowups: snapshot.inspector.readonly_followups,
  assessments: snapshot.assessments?.items ?? [],
  s3Outcome: snapshot.inspector.trusted_state.s3_outcome as Record<string, unknown> | null,
});
const itemIds = (projection: ReturnType<typeof projectConversation>, sourceId: string) =>
  projection.threads.find((thread) => thread.anchor.message_id === sourceId)?.items.map((item) => item.id) ?? [];

if (mode === 'initial') {
  const snapshot = data.authorized;
  const projection = project(snapshot);
  console.log(JSON.stringify({ mode, task_id: data.ids.task_id,
    api_runs: snapshot.inspector.runs.map((run) => ({ run_id: run.run_id, task_id: run.task_id ?? null,
      source_message_id: run.source_message_id })),
    initial_items: itemIds(projection, data.ids.initial_source),
    followup_items: itemIds(projection, data.ids.followup_source),
    unassociated: projection.unassociatedItems.map((item) => item.id) }));
  assert.ok(itemIds(projection, data.ids.initial_source).includes(`investigation:${data.ids.initial_run}`),
    'real Inspector initial Answer was not attached to its API Message');
  assert.ok(itemIds(projection, data.ids.followup_source).includes(`followup:${data.ids.followup_run}`),
    'real Inspector Follow-up was not attached to its API Message');
  for (const run of snapshot.inspector.runs) assert.equal(run.task_id, data.ids.task_id);

  const altered = (mutate: (copy: Snapshot) => void) => {
    const copy = structuredClone(snapshot);
    mutate(copy);
    return project(copy);
  };
  const wrongSource = altered((copy) => { copy.inspector.investigation_answers![0]!.source_message_id = data.ids.followup_source!; });
  assert.equal(itemIds(wrongSource, data.ids.followup_source).includes(`investigation:${data.ids.initial_run}`), false);
  const wrongRun = altered((copy) => { copy.inspector.investigation_answers![0]!.run_id = data.ids.followup_run!; });
  assert.equal(itemIds(wrongRun, data.ids.initial_source).includes(`investigation:${data.ids.followup_run}`), false);
  const differentTask = altered((copy) => { copy.inspector.investigation_answers![0]!.source_message_id = data.ids.other_source!; });
  assert.equal(itemIds(differentTask, data.ids.other_source).includes(`investigation:${data.ids.initial_run}`), false);
  const missingRun = altered((copy) => {
    copy.inspector.runs = copy.inspector.runs.filter((run) => run.run_id !== data.ids.initial_run);
  });
  assert.equal(itemIds(missingRun, data.ids.initial_source).includes(`investigation:${data.ids.initial_run}`), false);

  const revoked = project(data.revoked);
  const revokedOutcome = data.revoked.inspector.trusted_state.s3_outcome as Record<string, unknown> | undefined;
  assert.equal(revokedOutcome?.run_id, undefined, 'revoked Inspector must not return a diagnosis Run link');
  assert.equal(revokedOutcome?.receipt_id, undefined, 'revoked Inspector must not return a diagnosis receipt');
  const serialized = JSON.stringify(revoked);
  for (const restricted of data.restricted) assert.equal(serialized.includes(restricted), false, `revoked result leaked: ${restricted}`);
  console.log(JSON.stringify({ mode, negative_cases: 'passed', revoked_projection: 'restricted results absent' }));
} else if (mode === 'correction') {
  const snapshot = data.confirmed;
  const projection = project(snapshot);
  const thread = projection.threads.find((item) => item.anchor.message_id === data.ids.question);
  const result = thread?.items.find((item) => item.id === `investigation:${data.ids.run}`);
  console.log(JSON.stringify({ mode, task_id: data.ids.task_id, question: data.ids.question,
    correction_message: data.ids.correction, run: data.ids.run, receipt: data.ids.receipt,
    api_run: snapshot.inspector.runs.find((run) => run.run_id === data.ids.run),
    thread_items: thread?.items.map((item) => item.id) ?? [],
    unassociated: projection.unassociatedItems.map((item) => item.id) }));
  assert.ok(result, 'persisted correction Answer was not attached to the original correction question');
  assert.equal(result.answer?.source_message_id, data.ids.correction);
  assert.equal(result.answer?.result_state, data.ids.result_state);
  assert.equal(result.runId, data.ids.run);
  assert.equal(result.diagnosis?.receipt_id, data.ids.receipt);
  assert.equal(result.diagnosis?.run_id, data.ids.run);
  assert.equal(projection.threads.some((item) => item.anchor.message_id === data.ids.correction), false);
  console.log(JSON.stringify({ mode, persisted_answer_and_diagnosis: 'attached', state: data.ids.result_state }));
} else if (mode === 'chat') {
  assert.ok(data.chat, 'actual Chat API snapshot is required');
  const projection = project(data.chat);
  const thread = projection.threads.find((item) => item.anchor.message_id === data.ids.question);
  const answers = thread?.items.filter((item) => item.kind === 'CHAT_MESSAGE' && item.message?.message_id === data.ids.answer) ?? [];
  assert.equal(answers.length, 1, 'persisted Chat answer must appear once under its exact API source Message');
  assert.equal(answers[0]?.message?.body, data.ids.answer_text);
  assert.equal(answers[0]?.runId, data.ids.run);
  assert.equal(projection.unassociatedItems.some((item) => item.id === `message:${data.ids.answer}`), false);
  console.log(JSON.stringify({ mode, question: data.ids.question, run: data.ids.run,
    answer: data.ids.answer, exact_message_projection: 'passed once' }));
} else {
  throw new Error(`unsupported test mode: ${mode}`);
}
