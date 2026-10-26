import type {
  ChatChunk, MessageItem, RunItem,
} from './api';

export interface ConversationAnswer {
  run_id: string;
  source_message_id: string;
  answer_text: string;
  result_state: string;
  source_refs: Array<Record<string, unknown>>;
  result?: Record<string, unknown>;
  currentness?: string;
  created_at: string;
  report_ref?: string;
}

export interface ConversationFollowup {
  run_id: string;
  source_message_id: string;
  expected_control_revision: number;
  result_state: string | null;
  answer_text: string | null;
  source_refs: Array<Record<string, unknown>>;
  result: Record<string, unknown>;
  reason_code?: string | null;
  created_at: string;
  completed_at?: string | null;
  run_status: string;
}

export interface ConversationRun extends Partial<RunItem> {
  run_id: string;
  task_id: string | null;
  source_message_id: string | null;
  kind: string;
  status: string;
  blocked_reason?: string | null;
  waiting_reason?: string | null;
  created_at: string;
  started_at?: string | null;
  ended_at?: string | null;
}

export interface ConversationAssessment {
  assessment_id: string;
  source_message_id: string;
  target_task_id?: string;
  task_id?: string;
  intent: string;
  follow_up_action?: string;
  status: string;
  failure_code?: string | null;
  correction_message_id?: string | null;
  investigation_run_id?: string | null;
  change_summary?: string | null;
  original_message?: string;
  proposal?: Record<string, unknown> | null;
}

export interface ConversationItem {
  id: string;
  kind: 'CHAT_MESSAGE' | 'INVESTIGATION_ANSWER' | 'READONLY_FOLLOWUP'
    | 'CORRECTION_ASSESSMENT' | 'RUN_STATUS' | 'STREAM';
  createdAt: string;
  runId?: string;
  message?: MessageItem;
  answer?: ConversationAnswer;
  followup?: ConversationFollowup;
  assessment?: ConversationAssessment;
  correctionMessage?: MessageItem;
  run?: ConversationRun;
  chunks?: ChatChunk[];
  diagnosis?: Record<string, unknown>;
}

export interface ConversationThread {
  anchor: MessageItem;
  items: ConversationItem[];
}

export interface ConversationProjection {
  threads: ConversationThread[];
  unassociatedItems: ConversationItem[];
}

export interface ProjectConversationInput {
  messages: MessageItem[];
  runs?: ConversationRun[];
  investigationAnswers?: ConversationAnswer[];
  readonlyFollowups?: ConversationFollowup[];
  assessments?: ConversationAssessment[];
  activeChatRun?: ConversationRun | null;
  chunks?: ChatChunk[];
  s3Outcome?: Record<string, unknown> | null;
}

export interface SessionEventDisplay {
  event_seq: number;
  event_kind: string;
  happened_at: string;
}

export function projectSessionEvent(event: SessionEventDisplay & { payload?: unknown }): SessionEventDisplay {
  return {
    event_seq: event.event_seq,
    event_kind: event.event_kind,
    happened_at: event.happened_at,
  };
}

export interface CachedS3Inspector {
  task: Record<string, unknown>;
  trusted_state: Record<string, unknown>;
  current_gate: Record<string, unknown>;
  runs: ConversationRun[];
  evidence: unknown[];
  observations: unknown[];
  investigation_answers?: ConversationAnswer[];
  readonly_followups?: ConversationFollowup[];
  task_input_messages?: Array<Record<string, unknown>>;
  investigation_model_traces?: unknown[];
  chat_model_attempts?: unknown[];
  chat_context_provenance?: unknown[];
  investigator_context_provenance?: unknown[];
}

export function s3InspectorAuthorizationUnavailable(
  inspector: Pick<CachedS3Inspector, 'task' | 'trusted_state'> | null,
): boolean {
  if (!inspector || inspector.task.service_id !== 'orders-async-demo') return false;
  const outcome = inspector.trusted_state.s3_outcome;
  if (!outcome || typeof outcome !== 'object') return false;
  const record = outcome as Record<string, unknown>;
  const gate = record.gate;
  return record.currentness === 'INVALIDATED_BY_CURRENT_FACTS'
    && !!gate && typeof gate === 'object'
    && (gate as Record<string, unknown>).reason_code === 'S3_AUTHORIZATION_UNAVAILABLE';
}

export function clearS3RestrictedResultCache<T extends CachedS3Inspector>(
  inspector: T | null,
  messages: MessageItem[],
  taskId: string,
): { inspector: T | null; messages: MessageItem[] } {
  if (!inspector || inspector.task.task_id !== taskId || inspector.task.service_id !== 'orders-async-demo') {
    return { inspector, messages };
  }
  const runIds = new Set(inspector.runs.map((run) => run.run_id));
  const followupSources = new Set((inspector.readonly_followups ?? []).map((item) => item.source_message_id));
  const hiddenFollowupRunIds = new Set([
    ...(inspector.readonly_followups ?? []).map((item) => item.run_id),
    ...inspector.runs.filter((run) => run.source_message_id && followupSources.has(run.source_message_id))
      .map((run) => run.run_id),
  ]);
  const sourceMessageIds = new Set([
    ...(inspector.task_input_messages ?? []).map((item) => String(item.message_id ?? '')),
    ...(inspector.investigation_answers ?? []).map((item) => item.source_message_id),
    ...(inspector.readonly_followups ?? []).map((item) => item.source_message_id),
  ].filter(Boolean));
  const visibleMessages = messages.filter((message) => {
    if (message.role !== 'ASSISTANT') return true;
    return message.task_id !== taskId
      && !(message.answer_run_id && runIds.has(message.answer_run_id))
      && !(message.answer_source_message_id && sourceMessageIds.has(message.answer_source_message_id));
  });
  const trustedState = { ...inspector.trusted_state };
  delete trustedState.s3_outcome;
  delete trustedState.s3_handoff;
  const clearedInspector = {
    ...inspector,
    runs: inspector.runs.filter((run) => !hiddenFollowupRunIds.has(run.run_id)),
    trusted_state: {
      ...trustedState,
      s3_outcome: {
        outcome: 'INCONCLUSIVE',
        currentness: 'INVALIDATED_BY_CURRENT_FACTS',
        recovered: false,
        gate: { decision: 'INCONCLUSIVE', reason_code: 'S3_AUTHORIZATION_UNAVAILABLE' },
      },
    },
    current_gate: { decision: 'INCONCLUSIVE', reason_code: 'S3_AUTHORIZATION_UNAVAILABLE', checked_fact_ids: [] },
    evidence: [],
    observations: [],
    investigation_answers: [],
    readonly_followups: [],
    investigation_model_traces: [],
    chat_context_provenance: [],
    investigator_context_provenance: [],
  } as T;
  return { inspector: clearedInspector, messages: visibleMessages };
}

function taskMatches(anchor: MessageItem, taskId: string | null | undefined): boolean {
  return sameTask(anchor.task_id, taskId);
}

function sameTask(left: string | null | undefined, right: string | null | undefined): boolean {
  return (left ?? null) === (right ?? null);
}

function itemTime(item: ConversationItem): string {
  return item.createdAt || '';
}

function addUnique(items: ConversationItem[], byId: Map<string, ConversationItem>, item: ConversationItem): void {
  if (byId.has(item.id)) return;
  byId.set(item.id, item);
  items.push(item);
}

export function projectConversation(input: ProjectConversationInput): ConversationProjection {
  const assessments = input.assessments ?? [];
  const uniqueMessages = [...new Map(input.messages.map((message) => [message.message_id, message])).values()];
  const messagesById = new Map(uniqueMessages.map((message) => [message.message_id, message]));
  const linkedCorrectionIds = new Set<string>();
  for (const assessment of assessments) {
    const correction = assessment.correction_message_id
      ? messagesById.get(assessment.correction_message_id)
      : undefined;
    const source = messagesById.get(assessment.source_message_id);
    if (correction && correction.role === 'USER' && correction.input_kind === 'CORRECT_TASK_INPUT'
      && source?.role === 'USER' && taskMatches(source, assessment.target_task_id ?? assessment.task_id)
      && taskMatches(correction, assessment.target_task_id ?? assessment.task_id)) {
      linkedCorrectionIds.add(correction.message_id);
    }
  }

  const anchors = uniqueMessages
    .filter((message) => message.role === 'USER' && !linkedCorrectionIds.has(message.message_id))
    .sort((left, right) => left.sequence - right.sequence || left.message_id.localeCompare(right.message_id));
  const threads: ConversationThread[] = anchors.map((anchor) => ({ anchor, items: [] }));
  const threadByMessageId = new Map(threads.map((thread) => [thread.anchor.message_id, thread]));
  const idsByThread = new Map(threads.map((thread) => [thread.anchor.message_id, new Map<string, ConversationItem>()]));
  const unassociatedItems: ConversationItem[] = [];
  const unassociatedIds = new Set<string>();
  const attach = (sourceMessageId: string | null | undefined, taskId: string | null | undefined, item: ConversationItem): boolean => {
    const thread = sourceMessageId ? threadByMessageId.get(sourceMessageId) : undefined;
    if (!thread || !taskMatches(thread.anchor, taskId)) return false;
    const ids = idsByThread.get(thread.anchor.message_id)!;
    addUnique(thread.items, ids, item);
    return true;
  };
  const orphan = (item: ConversationItem): void => {
    if (unassociatedIds.has(item.id)) return;
    unassociatedIds.add(item.id);
    unassociatedItems.push(item);
  };

  for (const message of uniqueMessages) {
    if (message.role === 'USER') continue;
    const sourceId = message.answer_source_message_id ?? null;
    const source = sourceId ? messagesById.get(sourceId) : undefined;
    const valid = message.role === 'ASSISTANT' && !!source && source.role === 'USER'
      && taskMatches(message, source.task_id) && !!message.answer_run_id
      && !!message.answer_kind && attach(sourceId, message.task_id, {
        id: `message:${message.message_id}`, kind: 'CHAT_MESSAGE', createdAt: message.created_at,
        runId: message.answer_run_id, message,
      });
    if (!valid) {
      const item: ConversationItem = {
        id: `message:${message.message_id}`, kind: 'CHAT_MESSAGE', createdAt: message.created_at, message,
      };
      if (threadByMessageId.has(message.message_id)) continue;
      orphan(item);
    }
  }

  for (const answer of input.investigationAnswers ?? []) {
    const item: ConversationItem = {
      id: `investigation:${answer.run_id}`, kind: 'INVESTIGATION_ANSWER', createdAt: answer.created_at,
      runId: answer.run_id, answer,
    };
    if (!attach(answer.source_message_id, input.runs?.find((run) => run.run_id === answer.run_id)?.task_id, item)) orphan(item);
  }

  for (const followup of input.readonlyFollowups ?? []) {
    const run = input.runs?.find((candidate) => candidate.run_id === followup.run_id);
    const item: ConversationItem = {
      id: `followup:${followup.run_id}`, kind: 'READONLY_FOLLOWUP',
      createdAt: followup.completed_at ?? followup.created_at, runId: followup.run_id, followup,
    };
    if (!attach(followup.source_message_id, run?.task_id, item)) orphan(item);
  }

  for (const assessment of assessments) {
    if (assessment.intent === 'FOLLOW_UP' && assessment.status === 'NO_UPDATE' && !assessment.failure_code) continue;
    const taskId = assessment.target_task_id ?? assessment.task_id ?? null;
    const correctionMessage = assessment.correction_message_id
      ? messagesById.get(assessment.correction_message_id)
      : undefined;
    const item: ConversationItem = {
      id: `assessment:${assessment.assessment_id}`, kind: 'CORRECTION_ASSESSMENT',
      createdAt: correctionMessage?.created_at ?? uniqueMessages.find((message) => message.message_id === assessment.source_message_id)?.created_at ?? '',
      assessment,
      correctionMessage: correctionMessage?.role === 'USER' && correctionMessage.input_kind === 'CORRECT_TASK_INPUT'
        ? correctionMessage : undefined,
    };
    if (!attach(assessment.source_message_id, taskId, item)) orphan(item);
  }

  const allRuns = new Map<string, ConversationRun>();
  for (const run of input.runs ?? []) allRuns.set(run.run_id, run);
  if (input.activeChatRun) allRuns.set(input.activeChatRun.run_id, input.activeChatRun);
  const active = input.activeChatRun;
  const correctedRunSources = new Map<string, string>();
  for (const assessment of assessments) {
    if (!assessment.investigation_run_id || !assessment.correction_message_id) continue;
    const run = allRuns.get(assessment.investigation_run_id);
    const correction = messagesById.get(assessment.correction_message_id);
    const taskId = assessment.target_task_id ?? assessment.task_id ?? null;
    if (run?.source_message_id === assessment.correction_message_id && correction?.role === 'USER'
      && correction.input_kind === 'CORRECT_TASK_INPUT' && taskMatches(correction, taskId)
      && sameTask(taskId, run.task_id)) {
      correctedRunSources.set(run.run_id, assessment.source_message_id);
    }
  }
  const answeredRuns = new Set<string>();
  for (const thread of threads) {
    for (const item of thread.items) if (item.runId) answeredRuns.add(item.runId);
  }

  for (const run of allRuns.values()) {
    if (!run.source_message_id) continue;
    const reason = run.blocked_reason ?? run.waiting_reason ?? '';
    if (reason === 'FOLLOWUP_ROUTED_TO_INVESTIGATOR'
      || reason === 'UPDATE_CLASSIFICATION_PENDING' || reason === 'UPDATE_CONFIRMATION_PENDING') continue;
    if (active?.run_id === run.run_id && run.status === 'RUNNING' && (input.chunks?.length ?? 0) > 0) continue;
    if (answeredRuns.has(run.run_id)) continue;
    const item: ConversationItem = {
      id: `run:${run.run_id}`, kind: 'RUN_STATUS', createdAt: run.started_at ?? run.created_at,
      runId: run.run_id, run,
    };
    const effectiveSource = correctedRunSources.get(run.run_id) ?? run.source_message_id;
    if (!attach(effectiveSource, run.task_id, item)) orphan(item);
  }

  if (active?.status === 'RUNNING' && active.source_message_id && (input.chunks?.length ?? 0) > 0) {
    const chunks = [...new Map((input.chunks ?? []).map((chunk) => [chunk.chunk_id, chunk])).values()]
      .sort((left, right) => left.chunk_seq - right.chunk_seq);
    const item: ConversationItem = {
      id: `stream:${active.run_id}`, kind: 'STREAM', createdAt: active.started_at ?? active.created_at,
      runId: active.run_id, run: active, chunks,
    };
    if (!attach(active.source_message_id, active.task_id, item)) orphan(item);
  }

  const diagnosis = input.s3Outcome;
  const receiptId = diagnosis?.receipt_id;
  if (receiptId) {
    const answer = (input.investigationAnswers ?? []).find((candidate) => candidate.report_ref === receiptId);
    if (answer) {
      const thread = threadByMessageId.get(answer.source_message_id);
      const projectedAnswer = thread?.items.find((item) => item.kind === 'INVESTIGATION_ANSWER' && item.runId === answer.run_id);
      if (projectedAnswer) projectedAnswer.diagnosis = diagnosis;
    }
  }

  for (const thread of threads) thread.items.sort((left, right) =>
    itemTime(left).localeCompare(itemTime(right)) || left.id.localeCompare(right.id));
  return {
    threads,
    unassociatedItems: unassociatedItems.sort((left, right) =>
      itemTime(left).localeCompare(itemTime(right)) || left.id.localeCompare(right.id)),
  };
}
