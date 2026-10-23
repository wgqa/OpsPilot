export interface SessionItem {
  session_id: string;
  created_at: string;
  updated_at: string;
  task_count: number;
}

export interface SessionDetail {
  session_id: string;
  tasks: Array<{ task_id: string; linked_at: string; is_primary: number }>;
}

export interface MessageItem {
  message_id: string;
  task_id: string | null;
  sequence: number;
  role: 'USER' | 'ASSISTANT' | 'SYSTEM';
  input_kind: string;
  body: string;
  created_at: string;
  application_state: string | null;
  applied_run_id: string | null;
}

export interface InvestigationUpdateProposal {
  proposal_id: string;
  operation_id: string;
  source_message_id: string;
  target_task_id: string;
  expected_control_revision: number;
  current_input: string;
  proposed_input: string;
  change_summary: string;
  status: string;
  provenance: 'USER_INPUT_UNTRUSTED';
}

export interface InvestigationUpdateAssessment {
  assessment_id: string;
  proposal_id: string | null;
  operation_id: string;
  source_message_id: string;
  target_task_id: string;
  intent: string;
  status: string;
  expected_control_revision: number;
  current_control_revision: number;
  original_message: string;
  change_summary: string;
  proposal: InvestigationUpdateProposal | null;
  correction_message_id: string | null;
  investigation_run_id: string | null;
  model_attempt: Record<string, unknown> | null;
  failure_code: string | null;
}

export interface RunItem {
  run_id: string;
  task_id: string | null;
  session_id: string;
  source_message_id: string | null;
  kind: string;
  status: string;
  waiting_reason: string | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  answer_status: string | null;
}

export interface ChatChunk {
  chunk_id: string;
  chunk_seq: number;
  body: string;
  body_digest: string;
  created_at: string;
  attempt_id: string;
}

export interface Inspector {
  task: Record<string, unknown>;
  trusted_state: Record<string, unknown>;
  plan_history: Array<Record<string, unknown>>;
  evidence: Array<Record<string, unknown>>;
  observations: Array<Record<string, unknown>>;
  runs: Array<Record<string, unknown>>;
  investigation_model_traces: Array<Record<string, unknown>>;
  chat_model_attempts: Array<Record<string, unknown>>;
  chat_context_provenance: Array<Record<string, unknown>>;
  task_input_messages: Array<Record<string, unknown>>;
  investigator_context_provenance: Array<Record<string, unknown>>;
  current_gate: Record<string, unknown>;
}

export interface PendingApproval {
  task_id: string;
  plan_hash: string;
  plan_version: number;
  created_at: string;
  service_id: string;
  integration_id: string;
  ticket_id: string;
  control_revision: number;
  pending_critical_message_seq: number | null;
}

export interface PlanReview {
  task_id: string;
  plan_hash: string;
  plan: Record<string, unknown>;
  current_state: Record<string, unknown>;
  evidence: Array<Record<string, unknown>>;
  scope: Record<string, unknown>;
}

export interface ApprovalResult {
  status: string;
  task_id: string;
  plan_hash: string;
  decision: 'APPROVED' | 'REJECTED';
  approval_id: string;
  resume_run_id: string;
  source_run_id?: string;
  run_status?: string;
  replayed: boolean;
}

export interface TaskOutcome {
  task_id: string;
  task_status: string;
  business_outcome: string;
  control_revision?: number;
  currentness?: string;
  submitted?: boolean;
  scope_authorized?: boolean;
  recovered?: boolean;
  handoff_status?: string;
  queue_entry?: Record<string, unknown> | null;
  handoff_receipt?: Record<string, unknown> | null;
  diagnosis_receipt?: Record<string, unknown> | null;
  draft?: Record<string, unknown> | null;
  plan?: Record<string, unknown>;
  approval?: Record<string, unknown> | null;
  resume_link?: Record<string, unknown> | null;
  resume_run?: Record<string, unknown> | null;
  repair?: Record<string, unknown> | null;
  verification?: Record<string, unknown> | null;
  frozen_report?: Record<string, unknown> | null;
  delivery?: Record<string, unknown> | null;
  local_report?: Record<string, unknown> | null;
  ticket_entry_count?: number;
}

export interface S3OrderResource {
  order_id: string;
  order_status: string;
  order_version: number;
  contract_version: number;
  service_id: string;
  integration_id: string;
  route: string;
  principal_id: string;
  selection_status: string;
}

export interface S3HandoffRequest {
  operation_id: string;
  diagnosis_receipt_id: string;
  diagnosis_digest: string;
  expected_control_revision: number;
}

export interface MemoryRecord extends Record<string, unknown> {
  memory_id: string;
  problem_type: string;
  summary: string;
  source_task_id: string;
  source_outcome: string;
  source_refs: Array<Record<string, unknown>>;
  experience: Record<string, unknown>;
  state: 'CANDIDATE' | 'ACTIVE' | 'REVOKED';
  version: number;
  content_digest: string;
}

export interface TaskMemoryContext {
  task_id: string;
  source_memories: MemoryRecord[];
  applicable_memories: MemoryRecord[];
  excluded_memories?: Array<Record<string, unknown>>;
  context_provenance: Array<Record<string, unknown>>;
}

export interface SemanticMemoryRecord extends Record<string, unknown> {
  memory_id: string;
  project_id: string;
  memory_kind: 'ALIAS' | 'INTERFACE_CONVENTION' | 'WORK_CONSTRAINT';
  memory_key: string;
  content: string;
  content_digest: string;
  source_task_id: string;
  source_refs: Array<Record<string, unknown>>;
  state: 'CANDIDATE' | 'ACTIVE' | 'REVISED' | 'REVOKED' | 'EXPIRED';
  version: number;
  expires_at: string;
}

export interface SemanticMemoryContext {
  task_id: string;
  project_id: string;
  source_candidates: SemanticMemoryRecord[];
  active_project_memories: SemanticMemoryRecord[];
  excluded: Array<Record<string, unknown>>;
}

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly code: string) {
    super(code);
  }
}

export function explainError(error: unknown): string {
  if (!(error instanceof ApiError)) return '连接服务失败，请确认本地 OpsPilot 服务仍在运行。';
  if (error.status === 401) return error.code === 'INVALID_CREDENTIALS'
    ? '所选身份的本地口令不匹配，或服务尚未配置该身份的口令。'
    : '登录状态已过期，请重新登录。';
  if (error.status === 403) return error.code === 'ORIGIN_REJECTED' ? '请求来源未获准，浏览器写入已被拒绝。' : '此操作需要额外权限或有效的 CSRF 校验。';
  if (error.status === 404) return '记录不存在，或当前身份无权查看。';
  if (error.status === 409) return '当前状态不允许此操作；刷新状态后重试。';
  if (error.status === 422) return '输入不符合要求，请检查内容后重试。';
  if (error.status >= 500) return '本地服务暂时不可用；已提交内容会保留，可稍后刷新查看状态。';
  return `请求失败：${error.code}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', ...init });
  const data = await response.json().catch(() => ({})) as Record<string, unknown>;
  if (!response.ok) throw new ApiError(response.status, String(data.code ?? 'HTTP_ERROR'));
  return data as T;
}

export const api = {
  login(actor_id: string, password: string) {
    return request<{ actor_id: string; tenant_id: string; role: string; csrf_token: string }>('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actor_id, password }),
    });
  },
  me() { return request<{ actor_id: string; tenant_id: string; role: string }>('/api/auth/me'); },
  logout(csrf: string) {
    return request<{ status: string }>('/api/auth/logout', { method: 'POST', headers: writeHeaders(csrf) });
  },
  sessions() { return request<{ items: SessionItem[] }>('/api/sessions'); },
  session(sessionId: string) { return request<SessionDetail>(`/api/sessions/${encodeURIComponent(sessionId)}`); },
  createSession(csrf: string) {
    return request<SessionItem>('/api/sessions', { method: 'POST', headers: writeHeaders(csrf) });
  },
  messages(sessionId: string) { return request<{ items: MessageItem[] }>(`/api/sessions/${encodeURIComponent(sessionId)}/messages?limit=500`); },
  sessionRuns(sessionId: string) { return request<{ items: RunItem[] }>(`/api/sessions/${encodeURIComponent(sessionId)}/runs`); },
  send(sessionId: string, body: string, taskId: string | null, csrf: string, inputKind: 'CHAT_READONLY' | 'CORRECT_TASK_INPUT' = 'CHAT_READONLY') {
    return request<{ run_id: string; message_id: string; sequence: number; answer_status: string | null; input_kind: string }>(
      `/api/sessions/${encodeURIComponent(sessionId)}/messages`, {
        method: 'POST', headers: { ...writeHeaders(csrf), 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ body, task_id: taskId, input_kind: inputKind }),
      },
    );
  },
  assessTaskUpdate(taskId: string, sourceMessageId: string, csrf: string) {
    return request<InvestigationUpdateAssessment>(
      `/api/tasks/${encodeURIComponent(taskId)}/investigation-updates/proposals`, {
        method: 'POST',
        headers: { ...writeHeaders(csrf), 'Idempotency-Key': sourceMessageId },
        body: JSON.stringify({ source_message_id: sourceMessageId }),
      },
    );
  },
  investigationUpdates(taskId: string) {
    return request<{ items: InvestigationUpdateAssessment[] }>(
      `/api/tasks/${encodeURIComponent(taskId)}/investigation-updates`,
    );
  },
  confirmTaskUpdate(taskId: string, proposal: InvestigationUpdateProposal, csrf: string) {
    return request<{ status: string; message_id: string; run_id: string; proposal_id: string }>(
      `/api/tasks/${encodeURIComponent(taskId)}/investigation-updates/${encodeURIComponent(proposal.proposal_id)}/confirm`, {
        method: 'POST',
        headers: { ...writeHeaders(csrf), 'Idempotency-Key': proposal.operation_id },
        body: JSON.stringify({
          expected_control_revision: proposal.expected_control_revision,
          operation_id: proposal.operation_id,
        }),
      },
    );
  },
  cancelTaskUpdate(taskId: string, proposal: InvestigationUpdateProposal, csrf: string) {
    return request<{ status: string; proposal_id: string; replayed: boolean }>(
      `/api/tasks/${encodeURIComponent(taskId)}/investigation-updates/${encodeURIComponent(proposal.proposal_id)}/cancel`, {
        method: 'POST',
        headers: { ...writeHeaders(csrf), 'Idempotency-Key': proposal.operation_id },
        body: JSON.stringify({ operation_id: proposal.operation_id }),
      },
    );
  },
  s3OrderResources() { return request<{ items: S3OrderResource[] }>('/api/s3/order-resources'); },
  createTask(
    sessionId: string, initialMessage: string, csrf: string,
    investigationKind: 'AUTH_INCIDENT' | 'ASYNC_CALLBACK' = 'AUTH_INCIDENT', s3OrderId?: string,
  ) {
    return request<{ task_id: string; run_id: string; status: string }>(`/api/sessions/${encodeURIComponent(sessionId)}/tasks`, {
      method: 'POST', headers: { ...writeHeaders(csrf), 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ initial_message: initialMessage, investigation_kind: investigationKind, ...(s3OrderId ? { s3_order_id: s3OrderId } : {}) }),
    });
  },
  runs(taskId: string) { return request<{ items: RunItem[] }>(`/api/tasks/${encodeURIComponent(taskId)}/runs`); },
  run(runId: string) { return request<RunItem>(`/api/runs/${encodeURIComponent(runId)}`); },
  chunks(runId: string, afterSeq: number) {
    return request<{ items: ChatChunk[] }>(`/api/runs/${encodeURIComponent(runId)}/chunks?after_seq=${afterSeq}`);
  },
  inspector(taskId: string) { return request<Inspector>(`/api/tasks/${encodeURIComponent(taskId)}/inspector`); },
  pendingApprovals() { return request<{ items: PendingApproval[] }>('/api/approvals/pending'); },
  planReview(taskId: string, planHash: string) {
    return request<PlanReview>(`/api/tasks/${encodeURIComponent(taskId)}/plans/${encodeURIComponent(planHash)}/review`);
  },
  submitApproval(taskId: string, planHash: string, decision: 'APPROVED' | 'REJECTED', csrf: string) {
    return request<ApprovalResult>(
      `/api/tasks/${encodeURIComponent(taskId)}/plans/${encodeURIComponent(planHash)}/approval`, {
        method: 'POST', headers: { ...writeHeaders(csrf), 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ decision }),
      },
    );
  },
  outcome(taskId: string) { return request<TaskOutcome>(`/api/tasks/${encodeURIComponent(taskId)}/outcome`); },
  handoff(taskId: string) { return request<TaskOutcome>(`/api/tasks/${encodeURIComponent(taskId)}/handoff`); },
  taskOutcome(taskId: string) { return request<TaskOutcome>(`/api/tasks/${encodeURIComponent(taskId)}/outcome`); },
  s3Handoff(taskId: string) { return request<Record<string, unknown>>(`/api/tasks/${encodeURIComponent(taskId)}/s3-handoff`); },
  submitS3Handoff(taskId: string, payload: S3HandoffRequest, csrf: string) {
    return request<Record<string, unknown>>(`/api/tasks/${encodeURIComponent(taskId)}/s3-handoff/submit`, {
      method: 'POST', headers: { ...writeHeaders(csrf), 'Idempotency-Key': payload.operation_id },
      body: JSON.stringify(payload),
    });
  },
  taskMemories(taskId: string) {
    return request<TaskMemoryContext>(`/api/tasks/${encodeURIComponent(taskId)}/memories`);
  },
  createMemoryCandidate(taskId: string, csrf: string, idempotencyKey: string) {
    return request<MemoryRecord>(`/api/tasks/${encodeURIComponent(taskId)}/memories/candidates`, {
      method: 'POST', headers: { ...writeHeaders(csrf), 'Idempotency-Key': idempotencyKey }, body: JSON.stringify({}),
    });
  },
  memories(state?: string) {
    const query = state ? `?state=${encodeURIComponent(state)}` : '';
    return request<{ items: MemoryRecord[] }>(`/api/memories${query}`);
  },
  memory(memoryId: string) { return request<MemoryRecord>(`/api/memories/${encodeURIComponent(memoryId)}`); },
  confirmMemory(memoryId: string, csrf: string, idempotencyKey: string) {
    return request<MemoryRecord>(`/api/memories/${encodeURIComponent(memoryId)}/confirm`, {
      method: 'POST', headers: { ...writeHeaders(csrf), 'Idempotency-Key': idempotencyKey }, body: JSON.stringify({}),
    });
  },
  revokeMemory(memoryId: string, csrf: string, idempotencyKey: string) {
    return request<MemoryRecord>(`/api/memories/${encodeURIComponent(memoryId)}/revoke`, {
      method: 'POST', headers: { ...writeHeaders(csrf), 'Idempotency-Key': idempotencyKey }, body: JSON.stringify({}),
    });
  },
  taskSemanticMemories(taskId: string) {
    return request<SemanticMemoryContext>(`/api/tasks/${encodeURIComponent(taskId)}/semantic-memories`);
  },
  semanticReviewQueue(state?: string) {
    const query = state ? `?state=${encodeURIComponent(state)}` : '';
    return request<{ items: SemanticMemoryRecord[] }>(`/api/semantic-memories/review-queue${query}`);
  },
  createSemanticCandidate(
    taskId: string,
    payload: {
      memory_kind: SemanticMemoryRecord['memory_kind'];
      memory_key: string;
      content: string;
      source_message_id: string;
      ttl_days?: number;
      supersedes_memory_id?: string;
      expected_version?: number;
    },
    csrf: string,
    idempotencyKey: string,
  ) {
    return request<SemanticMemoryRecord>(
      `/api/tasks/${encodeURIComponent(taskId)}/semantic-memories/candidates`, {
        method: 'POST', headers: { ...writeHeaders(csrf), 'Idempotency-Key': idempotencyKey },
        body: JSON.stringify(payload),
      },
    );
  },
  confirmSemanticMemory(memoryId: string, csrf: string, idempotencyKey: string) {
    return request<SemanticMemoryRecord>(`/api/semantic-memories/${encodeURIComponent(memoryId)}/confirm`, {
      method: 'POST', headers: { ...writeHeaders(csrf), 'Idempotency-Key': idempotencyKey }, body: JSON.stringify({}),
    });
  },
  revokeSemanticMemory(memoryId: string, csrf: string, idempotencyKey: string) {
    return request<SemanticMemoryRecord>(`/api/semantic-memories/${encodeURIComponent(memoryId)}/revoke`, {
      method: 'POST', headers: { ...writeHeaders(csrf), 'Idempotency-Key': idempotencyKey }, body: JSON.stringify({}),
    });
  },
  submitHandoff(
    taskId: string,
    payload: {
      operation_id: string;
      draft_id: string;
      draft_digest: string;
      expected_control_revision: number;
      handoff_kind: 'SCOPE_REVIEW';
    },
    csrf: string,
  ) {
    return request<Record<string, unknown>>(
      `/api/tasks/${encodeURIComponent(taskId)}/handoff/submit`,
      {
        method: 'POST',
        headers: { ...writeHeaders(csrf), 'Idempotency-Key': payload.operation_id },
        body: JSON.stringify(payload),
      },
    );
  },
  eventHistory(sessionId: string, after: number) {
    return request<{ items: Array<Record<string, unknown>>; after: number }>(`/api/sessions/${encodeURIComponent(sessionId)}/events/history?after=${after}`);
  },
};

function writeHeaders(csrf: string): HeadersInit {
  return { 'X-CSRF-Token': csrf, 'Content-Type': 'application/json' };
}
