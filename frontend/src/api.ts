export interface SessionItem {
  session_id: string;
  created_at: string;
  updated_at: string;
  task_count: number;
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
  task_input_messages: Array<Record<string, unknown>>;
  investigator_context_provenance: Array<Record<string, unknown>>;
  current_gate: Record<string, unknown>;
}

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly code: string) {
    super(code);
  }
}

export function explainError(error: unknown): string {
  if (!(error instanceof ApiError)) return '连接服务失败，请确认本地 OpsPilot 服务仍在运行。';
  if (error.status === 401) return '登录状态已过期，请重新登录。';
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
  createTask(sessionId: string, initialMessage: string, csrf: string) {
    return request<{ task_id: string; run_id: string; status: string }>(`/api/sessions/${encodeURIComponent(sessionId)}/tasks`, {
      method: 'POST', headers: { ...writeHeaders(csrf), 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({ initial_message: initialMessage }),
    });
  },
  runs(taskId: string) { return request<{ items: RunItem[] }>(`/api/tasks/${encodeURIComponent(taskId)}/runs`); },
  run(runId: string) { return request<RunItem>(`/api/runs/${encodeURIComponent(runId)}`); },
  chunks(runId: string, afterSeq: number) {
    return request<{ items: ChatChunk[] }>(`/api/runs/${encodeURIComponent(runId)}/chunks?after_seq=${afterSeq}`);
  },
  inspector(taskId: string) { return request<Inspector>(`/api/tasks/${encodeURIComponent(taskId)}/inspector`); },
  eventHistory(sessionId: string, after: number) {
    return request<{ items: Array<Record<string, unknown>>; after: number }>(`/api/sessions/${encodeURIComponent(sessionId)}/events/history?after=${after}`);
  },
};

function writeHeaders(csrf: string): HeadersInit {
  return { 'X-CSRF-Token': csrf, 'Content-Type': 'application/json' };
}
