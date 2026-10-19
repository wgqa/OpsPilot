<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { api, explainError, type ApprovalResult, type ChatChunk, type Inspector, type MessageItem, type PendingApproval, type PlanReview, type RunItem, type SessionItem, type TaskOutcome } from './api';

interface UserContext { actor_id: string; tenant_id: string; role: string }
interface EventItem { event_seq: number; event_kind: string; happened_at: string; payload: Record<string, unknown> }

const actor = ref('support-a');
const password = ref('');
const user = ref<UserContext | null>(null);
const csrf = ref(sessionStorage.getItem('opspilot.csrf') ?? '');
const sessions = ref<SessionItem[]>([]);
const sessionId = ref('');
const messages = ref<MessageItem[]>([]);
const taskId = ref('');
const inspector = ref<Inspector | null>(null);
const taskOutcome = ref<TaskOutcome | null>(null);
const pendingApprovals = ref<PendingApproval[]>([]);
const selectedReview = ref<PlanReview | null>(null);
const approvalResult = ref<ApprovalResult | null>(null);
const sessionEvents = ref<EventItem[]>([]);
const draft = ref('');
const initialSymptom = ref('');
const correctionDraft = ref('');
const showTaskForm = ref(false);
const busy = ref(false);
const loading = ref(false);
const errorMessage = ref('');
const notice = ref('');
const activeChatRun = ref<RunItem | null>(null);
const chunks = ref<ChatChunk[]>([]);
const lastChunkSeq = ref(0);
const reconnectCount = ref(0);
const reconnectPaused = ref(false);
const narrowInspectorOpen = ref(false);
const conversationEnd = ref<HTMLElement | null>(null);

let eventSource: EventSource | null = null;
let reconnectTimer: number | undefined;
let runPollTimer: number | undefined;
let loadingChunksRunId: string | null = null;
let seenEventSeq = new Set<number>();

const canCreateTask = computed(() => user.value?.role === 'SUPPORT');
const isApprover = computed(() => user.value?.role === 'APPROVER');
const latestBusinessRun = computed(() => inspector.value?.runs.find((run) => run.kind !== 'CHAT_READONLY') ?? null);
const currentTaskStatus = computed(() => String(inspector.value?.trusted_state.task_status ?? inspector.value?.task.status ?? ''));
const displayStream = computed(() => activeChatRun.value?.status === 'RUNNING' && chunks.value.length > 0);
const latestContextProvenance = computed(() => inspector.value?.investigator_context_provenance[0] ?? null);
const latestSelectedInputs = computed(() => Array.isArray(latestContextProvenance.value?.selected_input_messages)
  ? latestContextProvenance.value.selected_input_messages as Array<Record<string, unknown>> : []);
const latestSelectedKnowledge = computed(() => Array.isArray(latestContextProvenance.value?.selected_knowledge)
  ? latestContextProvenance.value.selected_knowledge as Array<Record<string, unknown>> : []);

function dateLabel(value: unknown): string {
  if (typeof value !== 'string' || !value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString('zh-CN', { hour12: false });
}

function statusTone(value: unknown): string {
  const status = String(value ?? '').toUpperCase();
  if (['SUCCEEDED', 'COMPLETED', 'ENABLED', 'ACTIVE', 'APPROVED', 'READY', 'DELIVERED'].includes(status)) return 'good';
  if (['FAILED', 'BLOCKED', 'ABORTED', 'REJECTED', 'DISABLED', 'INCONCLUSIVE'].includes(status)) return 'bad';
  if (['WAITING_APPROVAL', 'WAITING_INPUT', 'QUEUED', 'RUNNING', 'INTERRUPTED_RECOVERABLE', 'RECOVERED_NOT_DELIVERED', 'APPROVAL_ACCEPTED', 'SCOPE_ESCALATED', 'PENDING_REVIEW', 'OVERDUE'].includes(status)) return 'warm';
  return 'neutral';
}

function readableStatus(value: unknown): string {
  const status = String(value ?? 'UNKNOWN');
  const names: Record<string, string> = {
    WAITING_APPROVAL: '等待审批', WAITING_INPUT: '等待补充信息', INTERRUPTED_RECOVERABLE: '等待恢复',
    QUEUED: '排队中', RUNNING: '执行中', SUCCEEDED: '已完成', COMPLETED: '已完成',
    FAILED: '失败', BLOCKED: '已阻止', INCONCLUSIVE: '结论不足', ENABLED: '已启用',
    DISABLED: '已停用', ACTIVE: '生效中', APPROVED: '已批准', REJECTED: '已拒绝',
    CHAT_READONLY: '只读聊天', INVESTIGATE: '调查', APPROVAL_RESUME: '审批恢复',
    SCOPE_ESCALATED: '已交本地队列', PENDING_REVIEW: '等待人工处理', OVERDUE: '超过处理目标',
  };
  return names[status] ?? status;
}

async function login(): Promise<void> {
  errorMessage.value = '';
  notice.value = '';
  busy.value = true;
  try {
    const result = await api.login(actor.value, password.value);
    user.value = { actor_id: result.actor_id, tenant_id: result.tenant_id, role: result.role };
    csrf.value = result.csrf_token;
    sessionStorage.setItem('opspilot.csrf', result.csrf_token);
    password.value = '';
    if (result.role === 'APPROVER') await loadPendingApprovals();
    else await loadSessions();
    notice.value = '已通过本地可信身份登录。';
  } catch (error) {
    errorMessage.value = explainError(error);
  } finally {
    busy.value = false;
  }
}

async function restoreLogin(): Promise<void> {
  try {
    user.value = await api.me();
    if (!csrf.value) notice.value = '登录已恢复；请重新登录一次以继续发送或创建会话。';
    if (user.value.role === 'APPROVER') await loadPendingApprovals();
    else await loadSessions();
  } catch {
    user.value = null;
  }
}

async function logout(): Promise<void> {
  try {
    if (csrf.value) await api.logout(csrf.value);
  } catch (error) {
    errorMessage.value = explainError(error);
  }
  stopEvents();
  user.value = null;
  csrf.value = '';
  sessionStorage.removeItem('opspilot.csrf');
  sessions.value = [];
  sessionId.value = '';
  messages.value = [];
  inspector.value = null;
  taskOutcome.value = null;
  pendingApprovals.value = [];
  selectedReview.value = null;
  approvalResult.value = null;
}

async function loadSessions(): Promise<void> {
  const response = await api.sessions();
  sessions.value = response.items;
  if (sessions.value.length > 0 && !sessions.value.some((item) => item.session_id === sessionId.value)) {
    await selectSession(sessions.value[0].session_id);
  }
}

async function loadPendingApprovals(): Promise<void> {
  pendingApprovals.value = (await api.pendingApprovals()).items;
}

async function selectPendingApproval(item: PendingApproval): Promise<void> {
  busy.value = true;
  errorMessage.value = '';
  approvalResult.value = null;
  try {
    selectedReview.value = await api.planReview(item.task_id, item.plan_hash);
  } catch (error) {
    selectedReview.value = null;
    errorMessage.value = explainError(error);
  } finally {
    busy.value = false;
  }
}

async function decideApproval(decision: 'APPROVED' | 'REJECTED'): Promise<void> {
  const review = selectedReview.value;
  if (!review || !csrf.value || busy.value) return;
  const action = decision === 'APPROVED' ? '批准' : '拒绝';
  const confirmed = window.confirm(
    `${action}当前不可变 Plan ${review.plan_hash.slice(0, 14)}？\n\n` +
    `目标：${String(review.plan.target_resource_id)}\n动作：REPAIR 与独立 DELIVER\n` +
    '批准会创建唯一恢复 Run；拒绝会保存拒绝报告且不执行写入。',
  );
  if (!confirmed) return;
  busy.value = true;
  errorMessage.value = '';
  try {
    approvalResult.value = await api.submitApproval(review.task_id, review.plan_hash, decision, csrf.value);
    notice.value = decision === 'APPROVED'
      ? '批准回执、恢复 Run 与事件已持久受理；受信 Worker 正在恢复原调查图。'
      : '拒绝回执与恢复 Run 已持久受理；原调查图将写入拒绝报告，不会修复。';
    await loadPendingApprovals();
  } catch (error) {
    errorMessage.value = explainError(error);
  } finally {
    busy.value = false;
  }
}

async function createSession(): Promise<void> {
  if (!csrf.value) {
    notice.value = '请重新登录以取得本页写入校验令牌。';
    return;
  }
  busy.value = true;
  errorMessage.value = '';
  try {
    const created = await api.createSession(csrf.value);
    sessions.value = [created as SessionItem, ...sessions.value];
    await selectSession(created.session_id);
  } catch (error) {
    errorMessage.value = explainError(error);
  } finally {
    busy.value = false;
  }
}

async function selectSession(value: string): Promise<void> {
  sessionId.value = value;
  taskId.value = '';
  messages.value = [];
  inspector.value = null;
  taskOutcome.value = null;
  sessionEvents.value = [];
  chunks.value = [];
  activeChatRun.value = null;
  errorMessage.value = '';
  stopEvents();
  await refreshSession();
}

async function refreshSession(): Promise<void> {
  if (!sessionId.value) return;
  loading.value = true;
  try {
    const response = await api.messages(sessionId.value);
    messages.value = response.items;
    const runs = await api.sessionRuns(sessionId.value);
    const chatRuns = [...runs.items].filter((run) => run.kind === 'CHAT_READONLY');
    const latestChat = chatRuns.at(-1) ?? null;
    const recoverable = [...chatRuns].reverse().find((run) => ['QUEUED', 'RUNNING', 'INTERRUPTED_RECOVERABLE'].includes(run.status));
    activeChatRun.value = recoverable ?? latestChat;
    if (recoverable) {
      chunks.value = await api.chunks(recoverable.run_id, 0).then((result) => result.items);
      lastChunkSeq.value = chunks.value.reduce((max, item) => Math.max(max, item.chunk_seq), 0);
      void watchRun(recoverable.run_id);
    } else if (latestChat && ['FAILED', 'BLOCKED'].includes(latestChat.status)) {
      errorMessage.value = `上次只读回答结束：${readableStatus(latestChat.status)}${latestChat.waiting_reason ? `（${latestChat.waiting_reason}）` : ''}`;
    }
    const linkedTask = [...response.items].reverse().find((item) => item.task_id)?.task_id;
    if (linkedTask) {
      taskId.value = linkedTask;
      await refreshInspector();
    }
    await refreshEventHistory();
    connectEvents();
  } catch (error) {
    errorMessage.value = explainError(error);
  } finally {
    loading.value = false;
  }
}

async function refreshInspector(): Promise<void> {
  if (!taskId.value) return;
  try {
    inspector.value = await api.inspector(taskId.value);
    if (user.value?.role === 'SUPPORT') taskOutcome.value = await api.handoff(taskId.value);
  } catch (error) {
    if (user.value?.role === 'APPROVER') errorMessage.value = explainError(error);
  }
}

async function createDemoTask(): Promise<void> {
  const symptom = initialSymptom.value.trim();
  if (!sessionId.value || !csrf.value || !symptom) return;
  busy.value = true;
  errorMessage.value = '';
  notice.value = '正在通过固定 S1 orders-demo / integration-a 绑定启动调查；故障描述作为未验证用户输入记录。';
  try {
    const created = await api.createTask(sessionId.value, symptom, csrf.value);
    initialSymptom.value = '';
    showTaskForm.value = false;
    taskId.value = created.task_id;
    await refreshSession();
    await watchRun(created.run_id);
  } catch (error) {
    errorMessage.value = explainError(error);
  } finally {
    busy.value = false;
  }
}

async function sendMessage(): Promise<void> {
  const body = draft.value.trim();
  if (!sessionId.value || !body || !csrf.value || busy.value) return;
  busy.value = true;
  errorMessage.value = '';
  notice.value = '';
  chunks.value = [];
  lastChunkSeq.value = 0;
  try {
    const accepted = await api.send(sessionId.value, body, taskId.value || null, csrf.value);
    draft.value = '';
    activeChatRun.value = await api.run(accepted.run_id);
    await refreshSessionMessagesOnly();
    await watchRun(accepted.run_id);
  } catch (error) {
    errorMessage.value = explainError(error);
  } finally {
    busy.value = false;
  }
}

async function submitCriticalCorrection(): Promise<void> {
  const body = correctionDraft.value.trim();
  if (!sessionId.value || !taskId.value || !body || !csrf.value || busy.value) return;
  const confirmed = window.confirm(
    '关键更正会中断当前业务调查 Run、提升 Task 控制版本并使旧 Plan/审批失效。\n\n确认这是正式纠错，并继续提交？',
  );
  if (!confirmed) return;
  busy.value = true;
  errorMessage.value = '';
  notice.value = '正在原子接收关键更正；旧 Run 与审批资格将由 TaskControl 重新裁决。';
  try {
    const accepted = await api.send(sessionId.value, body, taskId.value, csrf.value, 'CORRECT_TASK_INPUT');
    correctionDraft.value = '';
    await refreshSessionMessagesOnly();
    await refreshInspector();
    await watchRun(accepted.run_id);
  } catch (error) {
    errorMessage.value = explainError(error);
  } finally {
    busy.value = false;
  }
}

function stableHandoffOperationId(task: string, draftId: string, digest: string, revision: number): string {
  const storageKey = `opspilot.m2-03.handoff.${task}.${draftId}`;
  const stored = window.localStorage.getItem(storageKey);
  if (stored) {
    try {
      const parsed = JSON.parse(stored) as Record<string, unknown>;
      if (
        parsed.draft_digest === digest
        && parsed.expected_control_revision === revision
        && typeof parsed.operation_id === 'string'
        && parsed.operation_id.length > 0
      ) return parsed.operation_id;
    } catch {
      // Replace malformed local metadata; it contains no credential or session token.
    }
  }
  const operationId = crypto.randomUUID();
  window.localStorage.setItem(storageKey, JSON.stringify({
    operation_id: operationId,
    draft_digest: digest,
    expected_control_revision: revision,
  }));
  return operationId;
}

async function submitHandoff(): Promise<void> {
  const selectedTask = taskId.value;
  if (!selectedTask || !csrf.value || busy.value || user.value?.role !== 'SUPPORT') return;
  busy.value = true;
  errorMessage.value = '';
  notice.value = '';
  try {
    const displayed = await api.handoff(selectedTask);
    taskOutcome.value = displayed;
    if (displayed.business_outcome === 'SCOPE_ESCALATED' && displayed.handoff_receipt) {
      notice.value = `已由本地受控队列接收，回执 ${String(displayed.handoff_receipt.receipt_id)}；无需再次提交。`;
      return;
    }
    const displayedDraft = displayed.draft as Record<string, unknown> | null | undefined;
    if (
      displayed.business_outcome !== 'HANDOFF_READY'
      || displayed.currentness !== 'CURRENT'
      || !displayedDraft
      || displayed.submitted
    ) {
      errorMessage.value = '当前没有可提交的有效冻结草稿；请先刷新调查结果。';
      return;
    }
    const draftId = String(displayedDraft.draft_id ?? '');
    const digest = String(displayedDraft.content_digest ?? '');
    const revision = Number(displayed.control_revision);
    if (!draftId || !/^[0-9a-f]{64}$/.test(digest) || !Number.isInteger(revision) || revision < 0) {
      errorMessage.value = '冻结草稿或控制版本信息不完整，已停止提交。';
      return;
    }
    const confirmed = window.confirm(
      `确认将冻结草稿 ${draftId}（摘要 ${digest.slice(0, 16)}）提交到本地受控审查队列？\n\n`
      + '这只代表本地队列接收，不代表人工批准、Scope 授权或业务恢复。',
    );
    if (!confirmed) return;

    // Refresh after confirmation, then bind the write to the exact reviewed Draft/revision.
    const current = await api.handoff(selectedTask);
    taskOutcome.value = current;
    if (current.business_outcome === 'SCOPE_ESCALATED' && current.handoff_receipt) {
      notice.value = `本地队列已接收，回执 ${String(current.handoff_receipt.receipt_id)}；无需再次提交。`;
      return;
    }
    const currentDraft = current.draft as Record<string, unknown> | null | undefined;
    if (
      current.business_outcome !== 'HANDOFF_READY'
      || current.currentness !== 'CURRENT'
      || !currentDraft
      || String(currentDraft.draft_id ?? '') !== draftId
      || String(currentDraft.content_digest ?? '') !== digest
      || Number(current.control_revision) !== revision
    ) {
      errorMessage.value = '确认期间草稿或控制版本已变化；请重新核对后再提交。';
      return;
    }
    const operationId = stableHandoffOperationId(selectedTask, draftId, digest, revision);
    await api.submitHandoff(selectedTask, {
      operation_id: operationId,
      draft_id: draftId,
      draft_digest: digest,
      expected_control_revision: revision,
      handoff_kind: 'SCOPE_REVIEW',
    }, csrf.value);
    taskOutcome.value = await api.handoff(selectedTask);
    notice.value = `本地受控队列已接收，回执 ${String(taskOutcome.value.handoff_receipt?.receipt_id ?? '')}。尚未批准、未授予 Scope，业务未恢复。`;
    await refreshInspector();
  } catch (error) {
    errorMessage.value = explainError(error);
    // Reconcile a response that may have been lost after the Domain transaction committed.
    try {
      const reconciled = await api.handoff(selectedTask);
      taskOutcome.value = reconciled;
      if (reconciled.business_outcome === 'SCOPE_ESCALATED' && reconciled.handoff_receipt) {
        errorMessage.value = '';
        notice.value = `提交结果已从 Domain 回查：本地队列已接收，回执 ${String(reconciled.handoff_receipt.receipt_id)}。`;
      }
    } catch {
      // Keep the stable operation ID in localStorage so the next retry can reconcile it.
    }
  } finally {
    busy.value = false;
  }
}

function sourceKind(message: MessageItem): string | null {
  const trustedRef = inspector.value?.task_input_messages.find((item) => item.message_id === message.message_id);
  if (trustedRef) return String(trustedRef.kind ?? 'USER_INPUT_UNTRUSTED');
  const ref = latestSelectedInputs.value.find((item) => item.message_id === message.message_id);
  if (ref) return String(ref.kind ?? 'USER_INPUT_UNTRUSTED');
  if (message.input_kind === 'CORRECT_TASK_INPUT') return 'CRITICAL_CORRECTION';
  return null;
}

function readableInputKind(value: unknown): string {
  return value === 'INITIAL_SYMPTOM' ? '初始故障描述' : value === 'CRITICAL_CORRECTION' ? '关键更正' : '用户输入';
}

function readableGate(value: unknown): string {
  const gate = String(value ?? 'INCONCLUSIVE');
  return ({ READY: '证据满足 Plan 候选条件', DIAGNOSED: '可信 Scope 诊断通过', HANDOFF_READY: '申请草稿已冻结', NEED_MORE: '证据仍需补充', NO_ACTION: '当前事实不允许动作', INCONCLUSIVE: '证据不足或存在冲突' } as Record<string, string>)[gate] ?? gate;
}

function readableRunReason(value: unknown): string {
  const reason = String(value ?? '');
  if (reason === 'S1_SCOPE_CHANGE_UNSUPPORTED') return 'S1 仅能核实已绑定的订单路由。若只需只读调查，请提交关键更正明确范围。';
  if (reason === 'INPUT_REQUIRED') return '需要补充调查信息。';
  return reason;
}

async function refreshSessionMessagesOnly(): Promise<void> {
  if (!sessionId.value) return;
  messages.value = (await api.messages(sessionId.value)).items;
}

async function loadChunks(runId: string): Promise<void> {
  if (loadingChunksRunId === runId) return;
  loadingChunksRunId = runId;
  try {
    const response = await api.chunks(runId, lastChunkSeq.value);
    if (activeChatRun.value?.run_id !== runId || response.items.length === 0) return;
    const merged = new Map(chunks.value.map((chunk) => [chunk.chunk_seq, chunk]));
    for (const chunk of response.items) {
      if (!merged.has(chunk.chunk_seq)) merged.set(chunk.chunk_seq, chunk);
    }
    chunks.value = [...merged.values()].sort((left, right) => left.chunk_seq - right.chunk_seq);
    lastChunkSeq.value = Math.max(lastChunkSeq.value, ...response.items.map((item) => item.chunk_seq));
  } finally {
    if (loadingChunksRunId === runId) loadingChunksRunId = null;
  }
}

async function watchRun(runId: string): Promise<void> {
  if (runPollTimer !== undefined) window.clearInterval(runPollTimer);
  let polls = 0;
  await new Promise<void>((resolve) => {
    runPollTimer = window.setInterval(async () => {
      polls += 1;
      try {
        const run = await api.run(runId);
        if (run.kind === 'CHAT_READONLY') activeChatRun.value = run;
        if (run.kind === 'CHAT_READONLY') await loadChunks(runId);
        if (['SUCCEEDED', 'FAILED', 'BLOCKED', 'WAITING_APPROVAL', 'WAITING_INPUT'].includes(run.status) || polls >= 240) {
          if (runPollTimer !== undefined) window.clearInterval(runPollTimer);
          runPollTimer = undefined;
          await refreshSessionMessagesOnly();
          if (run.task_id) {
            taskId.value = run.task_id;
            await refreshInspector();
          }
          if (run.status === 'FAILED' || run.status === 'BLOCKED') {
            errorMessage.value = `本次运行结束：${readableStatus(run.status)}${run.waiting_reason ? `（${run.waiting_reason}）` : ''}`;
          }
          resolve();
        }
      } catch (error) {
        if (runPollTimer !== undefined) window.clearInterval(runPollTimer);
        runPollTimer = undefined;
        errorMessage.value = explainError(error);
        resolve();
      }
    }, 500);
  });
}

async function refreshEventHistory(): Promise<void> {
  if (!sessionId.value) return;
  const key = `opspilot.cursor.${sessionId.value}`;
  const cursor = Number(sessionStorage.getItem(key) ?? '0');
  const response = await api.eventHistory(sessionId.value, Number.isFinite(cursor) ? cursor : 0);
  for (const item of response.items) acceptEvent(item as unknown as EventItem);
}

function acceptEvent(item: EventItem): void {
  if (seenEventSeq.has(item.event_seq)) return;
  seenEventSeq.add(item.event_seq);
  sessionEvents.value.unshift(item);
  sessionEvents.value = sessionEvents.value.slice(0, 60);
  if (sessionId.value) sessionStorage.setItem(`opspilot.cursor.${sessionId.value}`, String(item.event_seq));
  const runId = String(item.payload.run_id ?? '');
  if (item.event_kind === 'CHAT_CHUNK_AVAILABLE' && runId && runId === activeChatRun.value?.run_id) {
    void loadChunks(runId);
  }
  if (item.event_kind.startsWith('RUN_STATUS_') || item.event_kind === 'CHAT_ANSWER_COMMITTED'
    || ['PLAN_APPROVED', 'PLAN_REJECTED', 'APPROVAL_RESUME_QUEUED', 'REPAIR_COMMITTED', 'REPORT_FROZEN', 'DELIVERY_COMMITTED'].includes(item.event_kind)) {
    void refreshSessionMessagesOnly();
    if (taskId.value) void refreshInspector();
  }
}

function connectEvents(): void {
  if (!sessionId.value || reconnectPaused.value || eventSource) return;
  const cursor = sessionStorage.getItem(`opspilot.cursor.${sessionId.value}`) ?? '0';
  const source = new EventSource(`/api/sessions/${encodeURIComponent(sessionId.value)}/events?after=${encodeURIComponent(cursor)}`);
  eventSource = source;
  source.onopen = () => { reconnectCount.value = 0; notice.value = ''; };
  const listener = (event: Event): void => {
    const message = event as MessageEvent<string>;
    const sequence = Number(message.lastEventId);
    if (!Number.isFinite(sequence) || sequence <= 0 || seenEventSeq.has(sequence)) return;
    try {
      acceptEvent({ event_seq: sequence, event_kind: message.type, happened_at: new Date().toISOString(),
                    payload: JSON.parse(message.data) as Record<string, unknown> });
    } catch {
      errorMessage.value = '收到无法解析的事件，已保留持久历史供刷新恢复。';
    }
  };
  for (const name of [
    'SESSION_CREATED', 'MESSAGE_ACCEPTED', 'TASK_CREATED', 'RUN_STATUS_QUEUED', 'RUN_STATUS_RUNNING',
    'RUN_STATUS_SUCCEEDED', 'RUN_STATUS_FAILED', 'RUN_STATUS_BLOCKED', 'RUN_STATUS_WAITING_APPROVAL',
    'RUN_STATUS_WAITING_INPUT', 'RUN_STATUS_INTERRUPTED_RECOVERABLE', 'CHAT_CHUNK_AVAILABLE',
    'CHAT_ANSWER_COMMITTED', 'CHAT_ATTEMPT_FAILED', 'RUN_RETRY_INTERRUPTED_RECOVERABLE', 'RUN_RETRY_BLOCKED',
    'PLAN_APPROVED', 'PLAN_REJECTED', 'APPROVAL_RESUME_QUEUED', 'REPAIR_COMMITTED',
    'REPORT_FROZEN', 'DELIVERY_COMMITTED',
  ]) source.addEventListener(name, listener);
  source.onerror = () => {
    source.close();
    if (eventSource === source) eventSource = null;
    reconnectCount.value += 1;
    if (reconnectCount.value > 5) {
      reconnectPaused.value = true;
      notice.value = '事件流多次中断；聊天记录仍保存在服务端，可手动重新连接。';
      return;
    }
    const delay = Math.min(15_000, 1_000 * (2 ** (reconnectCount.value - 1)));
    reconnectTimer = window.setTimeout(() => connectEvents(), delay);
  };
}

function reconnectEvents(): void {
  reconnectPaused.value = false;
  reconnectCount.value = 0;
  void refreshEventHistory().then(connectEvents).catch((error: unknown) => { errorMessage.value = explainError(error); });
}

function stopEvents(): void {
  eventSource?.close();
  eventSource = null;
  if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer);
  reconnectTimer = undefined;
}

function submitOnEnter(event: KeyboardEvent): void {
  if (!event.shiftKey) {
    event.preventDefault();
    void sendMessage();
  }
}

watch(taskId, () => { void refreshInspector(); });
watch([messages, chunks], () => conversationEnd.value?.scrollIntoView({ behavior: 'smooth', block: 'end' }));
onMounted(() => { void restoreLogin(); });
onBeforeUnmount(() => {
  stopEvents();
  if (runPollTimer !== undefined) window.clearInterval(runPollTimer);
});
</script>

<template>
  <main class="app-shell">
    <header class="topbar">
      <div class="brand-lockup">
        <div class="brand-mark" aria-hidden="true"><span></span><span></span><span></span></div>
        <div><strong>OpsPilot</strong><small>SUPPORT WORKSPACE</small></div>
      </div>
      <div class="topbar-right">
        <span class="local-status"><i></i>本地工作区</span>
        <template v-if="user">
          <span class="identity-pill"><b>{{ user.role }}</b><span>{{ user.actor_id }}</span></span>
          <button class="quiet-button" type="button" @click="logout">退出</button>
        </template>
      </div>
    </header>

    <section v-if="!user" class="login-screen">
      <div class="login-card">
        <div class="eyebrow">OPS CONTROL ROOM · LOCAL DEMO</div>
        <h1>登录 OpsPilot</h1>
        <p>使用本地可信身份进入受限演示工作区。</p>
        <form class="login-form" @submit.prevent="login">
          <label>演示身份
            <select v-model="actor" aria-label="演示身份">
              <option value="support-a">SUPPORT · support-a</option>
              <option value="approver-a">APPROVER · approver-a</option>
              <option value="support-b">SUPPORT · support-b</option>
              <option value="approver-b">APPROVER · approver-b</option>
            </select>
          </label>
          <label>本地口令
            <input v-model="password" type="password" autocomplete="current-password" required placeholder="从本地 .env 配置读取" />
          </label>
          <button class="primary-button login-submit" :disabled="busy" type="submit">{{ busy ? '正在登录…' : '登录工作台' }} <span>↗</span></button>
        </form>
        <p class="login-footnote">此演示仅绑定 loopback 本机地址，不代表生产 IAM。</p>
        <div v-if="errorMessage" class="alert error-alert" role="alert">{{ errorMessage }}</div>
      </div>
    </section>

    <section v-else-if="isApprover" class="approval-center">
      <div class="approval-heading">
        <div><span class="eyebrow">INDEPENDENT APPROVER · {{ user.tenant_id }}</span><h1>Plan 审批队列</h1><p>这里只显示当前租户等待审核的不可变计划。审批身份不能访问 Support 会话或代替其修改任务。</p></div>
        <button class="outline-button" type="button" :disabled="busy" @click="loadPendingApprovals">刷新待办</button>
      </div>
      <div class="approval-grid">
        <section class="approval-queue panel" aria-label="待审批计划">
          <div class="section-heading"><h2>待处理</h2><span class="section-count">{{ pendingApprovals.length }}</span></div>
          <div v-if="pendingApprovals.length === 0" class="muted-card">目前没有可审核的 S1 Plan。</div>
          <button
            v-for="item in pendingApprovals" :key="`${item.task_id}:${item.plan_hash}`"
            class="approval-queue-item" :class="{ selected: selectedReview?.plan_hash === item.plan_hash }"
            :data-plan-hash="item.plan_hash" type="button" :disabled="busy" @click="selectPendingApproval(item)"
          >
            <span class="status-badge warm">WAITING_APPROVAL</span>
            <strong>Task {{ item.task_id.slice(0, 18) }}</strong>
            <code>Plan {{ item.plan_hash.slice(0, 18) }}</code>
            <small>{{ item.service_id }} · {{ item.integration_id }} · {{ item.ticket_id }}</small>
          </button>
        </section>
        <section class="approval-review panel" aria-label="Plan 审核详情">
          <div v-if="selectedReview" data-testid="approval-review">
            <div class="approval-review-heading"><div><span class="eyebrow">FROZEN PLAN REVIEW</span><h2>核对动作范围</h2></div><span class="status-badge warm">待确认</span></div>
            <div class="review-identity"><span>Task</span><code>{{ selectedReview.task_id }}</code><span>Plan hash</span><code>{{ selectedReview.plan_hash }}</code></div>
            <div class="review-facts">
              <div><span>目标资源</span><b>{{ String(selectedReview.plan.target_resource_id) }}</b></div>
              <div><span>服务 / 集成</span><b>{{ String(selectedReview.plan.service_id) }} / {{ String(selectedReview.plan.integration_id) }}</b></div>
              <div><span>主体</span><b>{{ String(selectedReview.plan.principal_id) }}</b></div>
              <div><span>工单</span><b>{{ String(selectedReview.plan.ticket_id) }}</b></div>
              <div><span>凭证引用变更</span><b>{{ String(selectedReview.plan.old_credential_ref) }} → {{ String(selectedReview.plan.new_credential_ref) }}</b></div>
              <div><span>配置版本</span><b>{{ String(selectedReview.plan.expected_config_version) }} → {{ String((selectedReview.current_state.current_versions as Record<string, unknown> | null)?.config_version ?? '未知') }}</b></div>
              <div><span>主体 / 策略版本</span><b>{{ String(selectedReview.plan.expected_principal_version) }} / {{ String(selectedReview.plan.expected_auth_policy_version) }}</b></div>
              <div><span>任务控制版本</span><b>{{ String(selectedReview.current_state.control_revision) }}</b></div>
              <div><span>当前授权状态</span><b>{{ selectedReview.current_state.version_compatible ? '版本匹配，可审批' : '版本已变化，禁止批准' }}</b></div>
            </div>
            <div v-if="!selectedReview.current_state.version_compatible" class="alert warm-alert" role="status">
              当前资源与冻结 Plan 不兼容：{{ String(selectedReview.current_state.version_block_reason ?? 'PLAN_VERSION_MISMATCH') }}。可以拒绝此 Plan；批准会被服务端拒绝。
            </div>
            <div class="review-evidence"><div class="section-heading"><h3>Plan Evidence 引用</h3><span class="section-count">{{ selectedReview.evidence.length }}</span></div>
              <div v-for="item in selectedReview.evidence" :key="String(item.evidence_id)" class="review-evidence-item">
                <strong>{{ String(item.fact_type) }}</strong><code>{{ String(item.evidence_id) }}</code>
                <small>observed_versions {{ JSON.stringify(item.observed_versions) }}</small>
                <small>{{ JSON.stringify(item.facts) }}</small>
              </div>
            </div>
            <div class="approval-scope-warning">批准范围：一次配置 REPAIR 与独立 DELIVER。审批不会直接执行动作；恢复由可信 Worker 使用原调查 Graph 和服务端 executor 完成。</div>
            <div v-if="approvalResult" class="approval-result" data-testid="approval-result">
              <strong>{{ approvalResult.decision === 'APPROVED' ? '批准已持久受理' : '拒绝已持久受理' }}</strong>
              <small>Approval {{ approvalResult.approval_id }}</small>
              <small>恢复 Run {{ approvalResult.resume_run_id }} · {{ approvalResult.replayed ? '幂等回查' : '已排队' }}</small>
              <p v-if="approvalResult.decision === 'REJECTED'">该决定不会创建 REPAIR 或 DELIVER 写入。</p>
            </div>
            <div v-else class="approval-buttons">
              <button class="outline-button" type="button" data-testid="reject-plan" :disabled="busy || !csrf" @click="decideApproval('REJECTED')">拒绝 Plan</button>
              <button
                class="primary-button" type="button" data-testid="approve-plan"
                :disabled="busy || !csrf || !selectedReview.current_state.version_compatible"
                @click="decideApproval('APPROVED')"
              >批准并恢复原调查图 <span>→</span></button>
            </div>
          </div>
          <div v-else class="approval-empty"><div class="inspector-empty-icon">◈</div><h2>选择一个待审核 Plan</h2><p>审核视图只包含最小任务范围、当前 Domain 版本和 Plan 所引用的 MCP Evidence，不提供聊天记录或凭证秘密。</p></div>
          <div v-if="notice" class="notice-line" role="status">{{ notice }}</div>
          <div v-if="errorMessage" class="alert error-alert" role="alert">{{ errorMessage }}</div>
        </section>
      </div>
    </section>

    <section v-else class="workspace-grid">
      <aside class="session-rail panel">
        <div class="rail-heading">
          <div><span class="eyebrow">WORKSPACE</span><h2>会话</h2></div>
          <button class="icon-button" type="button" aria-label="新建会话" title="新建会话" :disabled="busy || !csrf" @click="createSession">＋</button>
        </div>
        <button class="new-session-button" type="button" :disabled="busy || !csrf" @click="createSession">＋ <span>新建会话</span></button>
        <div v-if="sessions.length === 0" class="empty-sessions">
          <div class="empty-glyph">▱</div><strong>还没有会话</strong><p>新建一个会话，开始解释调查证据或进行多轮问答。</p>
        </div>
        <nav v-else class="session-list" aria-label="会话列表">
          <button v-for="item in sessions" :key="item.session_id" class="session-item" :class="{ selected: item.session_id === sessionId }" type="button" @click="selectSession(item.session_id)">
            <span class="session-icon">◷</span><span class="session-copy"><strong>{{ item.session_id.slice(0, 22) }}</strong><small>{{ item.task_count }} 个关联 Task · {{ dateLabel(item.updated_at) }}</small></span>
            <span v-if="item.session_id === sessionId" class="selected-mark">●</span>
          </button>
        </nav>
        <div class="rail-footer"><span class="avatar">{{ user.actor_id.slice(-1).toUpperCase() }}</span><div><strong>{{ user.actor_id }}</strong><small>{{ user.tenant_id }} · {{ user.role }}</small></div></div>
      </aside>

      <section class="chat-panel panel" aria-label="聊天工作区">
        <div class="chat-toolbar">
          <div class="conversation-heading">
            <span class="eyebrow">PERSISTENT SESSION</span>
            <h1>{{ sessionId ? `会话 ${sessionId.slice(-8)}` : '欢迎使用 OpsPilot' }}</h1>
            <p><span class="live-dot"></span>{{ loading ? '正在加载持久消息…' : '消息与运行状态保存在本地 Domain' }}</p>
          </div>
          <div class="toolbar-actions">
            <span v-if="taskId" class="task-chip"><i></i>{{ taskId.slice(0, 16) }}</span>
            <button v-if="canCreateTask" class="outline-button" type="button" :disabled="!sessionId || busy || !csrf" @click="showTaskForm = !showTaskForm">＋ 新建调查任务</button>
            <button class="inspector-toggle" type="button" aria-label="显示 Task 检查器" @click="narrowInspectorOpen = !narrowInspectorOpen">▤</button>
          </div>
        </div>

        <div class="demo-notice"><span class="notice-icon">i</span><span>业务调查使用可信绑定 <b>orders-demo / integration-a</b> 与固定订单路由。用户描述和关键更正只提供调查线索，真实状态来自当前 MCP Evidence。</span></div>
        <form v-if="showTaskForm && canCreateTask" class="task-input-card" data-testid="new-task-form" @submit.prevent="createDemoTask">
          <div><span class="eyebrow">NEW INVESTIGATION</span><h2>描述实际故障</h2><p>请写下你观察到的现象。状态码未确认时可以明确说明；资源仍由服务端绑定。</p></div>
          <textarea v-model="initialSymptom" data-testid="initial-symptom-input" rows="3" maxlength="20000" placeholder="例如：昨晚凭证轮换后订单 API 一直提示未认证，请核实当前情况。" :disabled="busy || !csrf"></textarea>
          <div class="task-input-actions"><span>输入会以未验证用户来源加入 Investigator 上下文。</span><button class="primary-button" type="submit" :disabled="!initialSymptom.trim() || busy || !csrf">启动调查 <span>→</span></button></div>
        </form>

        <div class="conversation-scroll" data-testid="conversation" aria-live="polite">
          <div v-if="!sessionId" class="welcome-state">
            <div class="orbit-illustration"><span class="orbit-core">OP</span><i></i><b></b></div>
            <span class="eyebrow">INCIDENT RESPONSE, WITH EVIDENCE</span>
            <h2>从可信证据开始</h2>
            <p>创建会话后，你可以进行只读追问、提交实际故障描述启动 S1 调查，并查看来源明确的运行过程。</p>
            <button class="primary-button" :disabled="busy || !csrf" type="button" @click="createSession">创建第一个会话 <span>→</span></button>
          </div>
          <div v-else-if="messages.length === 0 && !loading" class="empty-conversation">
            <div class="message-orb">✳</div><h2>开始一段新的调查对话</h2><p>提出问题；回答会由配置的模型根据当前可访问事实生成。</p>
          </div>
          <article v-for="message in messages" :key="message.message_id" class="message-row" :class="message.role.toLowerCase()" :data-message-id="message.message_id">
            <div class="message-avatar">{{ message.role === 'USER' ? user.actor_id.slice(-1).toUpperCase() : '✳' }}</div>
            <div class="message-content">
              <div class="message-meta"><strong>{{ message.role === 'USER' ? user.actor_id : 'OpsPilot' }}</strong><span>{{ dateLabel(message.created_at) }}</span><span v-if="sourceKind(message)" class="message-task">{{ readableInputKind(sourceKind(message)) }} · 未验证</span><span v-else-if="message.role === 'USER' && message.task_id" class="message-task">只读对话</span></div>
              <div class="message-bubble">{{ message.body }}</div>
            </div>
          </article>
          <div v-if="displayStream" class="streaming-row" data-testid="live-stream">
            <div class="message-avatar assistant-avatar">✳</div>
            <div class="streaming-copy"><div class="message-meta"><strong>OpsPilot</strong><span class="streaming-label"><i></i>正在生成 · 暂存片段</span></div>
              <div class="stream-bubble" data-testid="stream-chunk">{{ chunks.map((chunk) => chunk.body).join('') }}<span class="typing-cursor"></span></div>
            </div>
          </div>
          <div v-else-if="activeChatRun && ['QUEUED', 'RUNNING'].includes(activeChatRun.status)" class="pending-row" data-testid="run-pending"><div class="loader"></div><span>{{ activeChatRun.status === 'QUEUED' ? '回答已进入持久队列…' : '模型正在组织回答…' }}</span></div>
          <div v-if="activeChatRun?.status === 'INTERRUPTED_RECOVERABLE'" class="alert warm-alert">回答在进程中断时留下了已保存的暂存片段，系统将在退避后恢复。片段不等同于最终回答。</div>
          <div ref="conversationEnd"></div>
        </div>

        <div class="composer-wrap">
          <div v-if="notice" class="notice-line" role="status">{{ notice }} <button v-if="reconnectPaused" type="button" @click="reconnectEvents">重新连接事件流</button></div>
          <div v-if="errorMessage" class="alert error-alert" role="alert">{{ errorMessage }}<button v-if="errorMessage.includes('登录状态')" type="button" @click="logout">重新登录</button></div>
          <form class="composer" @submit.prevent="sendMessage">
            <textarea v-model="draft" data-testid="message-input" :disabled="!sessionId || busy || !csrf" rows="2" placeholder="询问当前证据、任务状态，或继续上一轮对话…" @keydown.enter="submitOnEnter"></textarea>
            <div class="composer-bottom"><span><kbd>Enter</kbd> 发送 <kbd>Shift + Enter</kbd> 换行 · 只读聊天不能批准或修改业务对象</span><button class="send-button" :disabled="!sessionId || !draft.trim() || busy || !csrf" type="submit" aria-label="发送消息">{{ busy ? '…' : '↑' }}</button></div>
          </form>
          <div class="composer-footnote">回答只解释已授权信息。审批、修复和交付需要后续的可信控制流程。</div>
        </div>
      </section>

      <aside class="inspector-panel panel" :class="{ open: narrowInspectorOpen }" aria-label="Task 检查器">
        <div class="inspector-header"><div><span class="eyebrow">LIVE CONTEXT</span><h2>Task 检查器</h2></div><button class="icon-button close-inspector" aria-label="关闭检查器" type="button" @click="narrowInspectorOpen = false">×</button></div>
        <template v-if="inspector">
          <div class="task-summary-card" :data-task-id="String(inspector.task.task_id ?? taskId)">
            <div class="summary-top"><span class="task-symbol">◈</span><span class="status-badge" :class="statusTone(currentTaskStatus)"><i></i>{{ readableStatus(currentTaskStatus) }}</span></div>
            <span class="eyebrow">ACTIVE TASK</span><h3>{{ String(inspector.task.task_id ?? taskId).slice(0, 24) }}</h3>
            <p>{{ String(inspector.task.service_id ?? 'orders-demo') }} <span>·</span> {{ String(inspector.task.integration_id ?? 'integration-a') }}</p>
          </div>
          <div class="inspector-section">
            <div class="section-heading"><h3>当前运行</h3><span class="section-count">{{ inspector.runs.length }}</span></div>
            <div v-if="latestBusinessRun" class="run-card"><div class="run-icon">⌁</div><div class="run-copy"><strong>{{ readableStatus(latestBusinessRun.kind) }}</strong><small>{{ readableStatus(latestBusinessRun.status) }}<template v-if="latestBusinessRun.blocked_reason"> · {{ readableRunReason(latestBusinessRun.blocked_reason) }}</template></small></div><span class="status-dot" :class="statusTone(latestBusinessRun.status)"></span></div>
            <div v-else class="muted-card">尚未关联业务调查 Run。</div>
            <div v-if="activeChatRun" class="run-card chat-run-card"><div class="run-icon chat-run-icon">✳</div><div class="run-copy"><strong>只读聊天回答</strong><small>{{ readableStatus(activeChatRun.status) }}<template v-if="activeChatRun.waiting_reason"> · {{ activeChatRun.waiting_reason }}</template></small></div><span class="status-dot" :class="statusTone(activeChatRun.status)"></span></div>
          </div>
          <div class="inspector-section">
            <div class="section-heading"><h3>当前 Evidence</h3><span class="section-count">{{ inspector.evidence.length }}</span></div>
            <div v-if="inspector.evidence.length === 0" class="muted-card">当前 Task 尚无可展示的有效 MCP Evidence。</div>
            <div v-for="item in inspector.evidence" :key="String(item.evidence_id)" class="evidence-card">
              <div class="evidence-heading"><span class="evidence-type">{{ String(item.fact_type).replaceAll('_', ' ') }}</span><span class="verified-mark">✓ VERIFIED</span></div>
              <div class="evidence-facts"><template v-for="(value, key) in (item.facts as Record<string, unknown>)" :key="String(key)"><div><span>{{ String(key).replaceAll('_', ' ') }}</span><strong>{{ String(value) }}</strong></div></template></div>
              <div class="evidence-footer"><code>{{ String(item.evidence_id).slice(0, 22) }}</code><span>{{ dateLabel(item.fetched_at) }}</span></div>
            </div>
          </div>
          <div class="inspector-section">
            <div class="section-heading"><h3>计划与授权</h3><span class="read-only-label">只读</span></div>
            <div class="plan-card"><div class="plan-row"><span>最新 Plan</span><b>{{ inspector.trusted_state.plan ? String((inspector.trusted_state.plan as Record<string, unknown>).plan_hash).slice(0, 14) : '尚未生成' }}</b></div><div class="plan-row"><span>审批状态</span><b>{{ readableStatus((inspector.trusted_state.plan as Record<string, unknown> | null)?.approval_decision ?? 'UNKNOWN') }}</b></div><p v-if="currentTaskStatus === 'WAITING_APPROVAL'">Task 正等待同租户独立 APPROVER 审批。聊天文本不能代签或授予动作权限。</p><p v-else-if="currentTaskStatus">业务状态由可信 Domain 控制。用户线索与只读回答都不会改变审批资格或写入权限。</p>
              <div v-for="item in inspector.plan_history" :key="String(item.plan_hash)" class="plan-history-row"><code>{{ String(item.plan_hash).slice(0, 14) }}</code><span>{{ readableStatus(item.eligibility) }} · {{ readableStatus(item.approval_decision ?? 'UNKNOWN') }}</span></div>
            </div>
          </div>
          <div v-if="taskOutcome" class="inspector-section outcome-section" data-testid="task-outcome">
            <div class="section-heading"><h3>Domain 业务回执</h3><span class="status-badge" :class="statusTone(taskOutcome.business_outcome)">{{ String(taskOutcome.business_outcome) }}</span></div>
            <div v-if="taskOutcome.business_outcome === 'DELIVERED'" class="outcome-message good-outcome">同身份业务调用已恢复，冻结报告和工单交付回执均已核对。</div>
            <div v-else-if="taskOutcome.business_outcome === 'RECOVERED_NOT_DELIVERED'" class="outcome-message warm-outcome">业务已在线验证恢复，但工单尚未完成交付。</div>
            <div v-else-if="taskOutcome.business_outcome === 'REJECTED'" class="outcome-message warm-outcome">审批者已拒绝；拒绝报告来自原调查图，没有执行业务写入。</div>
            <div v-else-if="taskOutcome.business_outcome === 'HANDOFF_READY'" class="outcome-message warm-outcome">可信证据已完成诊断，权限申请草稿已冻结；尚未提交、未入队、权限未生效，S2 业务也未恢复。</div>
            <div v-else-if="taskOutcome.business_outcome === 'SCOPE_ESCALATED'" class="outcome-message warm-outcome" data-testid="handoff-accepted">本地受控队列已接收这份申请，当前等待人工处理。尚未批准、未授予 Scope，订单 API 仍未恢复。</div>
            <div v-else-if="taskOutcome.business_outcome === 'DIAGNOSED'" class="outcome-message warm-outcome">已形成可信诊断回执；申请草稿仍待冻结，尚未提交或改变任何授权。</div>
            <div v-else-if="taskOutcome.business_outcome === 'INCONCLUSIVE'" class="outcome-message warm-outcome">当前权限事实已变化或不足，旧诊断不能作为当前结论。</div>
            <div v-if="taskOutcome.diagnosis_receipt" class="outcome-row"><span>诊断回执</span><code>{{ String((taskOutcome.diagnosis_receipt as Record<string, unknown>).receipt_id) }}</code><span>Request {{ String((taskOutcome.diagnosis_receipt as Record<string, unknown>).request_id) }}</span></div>
            <div v-if="taskOutcome.draft" class="outcome-row"><span>冻结申请草稿</span><code>{{ String((taskOutcome.draft as Record<string, unknown>).draft_id) }}</code><span>摘要 {{ String((taskOutcome.draft as Record<string, unknown>).content_digest).slice(0, 16) }} · {{ taskOutcome.submitted ? '已交本地队列' : '未提交' }}</span></div>
            <div v-if="taskOutcome.draft" class="outcome-message warm-outcome">草稿中的缺失 Scope 仅供后续人工评估，不是授权结果：{{ JSON.stringify(((taskOutcome.draft as Record<string, unknown>).content as Record<string, unknown>).missing_scopes ?? []) }}</div>
            <button v-if="canCreateTask && taskId && taskOutcome.business_outcome === 'HANDOFF_READY' && taskOutcome.currentness === 'CURRENT' && !taskOutcome.submitted" class="primary-button" type="button" data-testid="submit-s2-handoff" :disabled="busy || !csrf" @click="submitHandoff">确认提交到本地受控队列</button>
            <div v-if="taskOutcome.handoff_receipt" class="outcome-row" data-testid="handoff-receipt"><span>HandoffReceipt</span><code>{{ String(taskOutcome.handoff_receipt.receipt_id) }}</code><span>Queue Entry {{ String(taskOutcome.handoff_receipt.queue_entry_id) }} · {{ readableStatus(taskOutcome.handoff_status ?? 'PENDING_REVIEW') }}</span></div>
            <div v-if="taskOutcome.queue_entry" class="outcome-row"><span>接收时间</span><span>{{ dateLabel(taskOutcome.queue_entry.received_at) }} · 截止 {{ dateLabel(taskOutcome.queue_entry.review_due_at) }}</span></div>
            <div v-if="taskOutcome.submitted" class="outcome-message warm-outcome">聊天只读追问不会再次入队。接收不等于批准、授权或业务恢复。</div>
            <div v-if="taskOutcome.approval" class="outcome-row">审批 <code>{{ String(taskOutcome.approval.approval_id) }}</code><span>{{ String(taskOutcome.approval.approver_id) }} · {{ String(taskOutcome.approval.decision) }}</span></div>
            <div v-if="taskOutcome.repair" class="outcome-row">REPAIR <code>{{ String(taskOutcome.repair.ledger_id) }}</code><span>配置 v{{ String(taskOutcome.repair.before_version) }} → v{{ String(taskOutcome.repair.after_version) }}</span></div>
            <div v-if="taskOutcome.verification" class="outcome-row">在线验证 <code>{{ String(taskOutcome.verification.verification_id) }}</code><span>HTTP {{ String(taskOutcome.verification.response_status) }} · {{ taskOutcome.verification.recovery_verified ? '业务字段通过' : '未恢复' }}</span></div>
            <div v-if="taskOutcome.frozen_report" class="outcome-row">冻结报告 <code>{{ String(taskOutcome.frozen_report.report_ref) }}</code><span>v{{ String(taskOutcome.frozen_report.report_version) }}</span></div>
            <div v-if="taskOutcome.delivery" class="outcome-row">DELIVER <code>{{ String(taskOutcome.delivery.delivery_id) }}</code><span>工单条目 {{ String(taskOutcome.delivery.ticket_entry_id) }}</span></div>
            <div v-if="taskOutcome.local_report" class="outcome-row">拒绝报告 <code>{{ String(taskOutcome.local_report.report_ref) }}</code><span>{{ String(taskOutcome.local_report.outcome) }}</span></div>
          </div>
          <div class="inspector-section input-provenance-section">
            <div class="section-heading"><h3>用户线索 Provenance</h3><span class="read-only-label">未验证</span></div>
            <div v-if="latestSelectedInputs.length === 0" class="muted-card">尚无模型调用上下文；已提交消息仍保存在会话与 Task Run 中。</div>
            <div v-for="item in latestSelectedInputs" :key="String(item.message_id ?? item.digest)" class="provenance-row">
              <span class="trace-icon">↳</span><span><strong>{{ readableInputKind(item.kind) }}</strong><small>{{ String(item.message_id ?? 'legacy fallback') }} · #{{ item.sequence ?? '—' }} · {{ String(item.provenance) }}</small><small>Digest {{ String(item.digest).slice(0, 16) }} · 控制版本 {{ item.applied_control_revision ?? item.accepted_control_revision ?? '—' }}</small></span>
            </div>
            <div v-if="latestContextProvenance?.task_run_control" class="run-control-meta">
              <span>Run <code>{{ String((latestContextProvenance.task_run_control as Record<string, unknown>).run_id ?? '—') }}</code></span>
              <span>当前控制版本 <b>{{ String((latestContextProvenance.task_run_control as Record<string, unknown>).current_control_revision ?? '—') }}</b></span>
              <span>消耗序号高水位 <b>{{ String((latestContextProvenance.task_run_control as Record<string, unknown>).consumed_message_seq ?? '—') }}</b></span>
            </div>
            <div v-if="latestContextProvenance?.selected_skill" class="trace-row"><span class="trace-icon model-icon">✳</span><span><strong>{{ String((latestContextProvenance.selected_skill as Record<string, unknown>).name) }} · v{{ String((latestContextProvenance.selected_skill as Record<string, unknown>).version) }}</strong><small>Skill SHA-256 {{ String((latestContextProvenance.selected_skill as Record<string, unknown>).digest).slice(0, 16) }}</small></span></div>
            <div v-for="item in latestSelectedKnowledge" :key="String(item.document_id)" class="trace-row"><span class="trace-icon">▤</span><span><strong>{{ String(item.document_id) }} · v{{ String(item.version) }}</strong><small>{{ String(item.source) }} · SHA-256 {{ String(item.digest).slice(0, 16) }}</small></span></div>
            <div class="gate-card"><span>确定性 Evidence Gate</span><b>{{ readableGate(inspector.current_gate.decision) }}</b><small>{{ String(inspector.current_gate.reason_code ?? '—') }} · 当前有效 Evidence {{ Array.isArray(inspector.current_gate.checked_fact_ids) ? (inspector.current_gate.checked_fact_ids as unknown[]).length : 0 }} 项</small></div>
          </div>
          <div v-if="canCreateTask && taskId" class="inspector-section correction-section">
            <div class="section-heading"><h3>正式关键更正</h3><span class="status-badge warm">会提升控制版本</span></div>
            <p class="correction-warning">提交后会中断正在运行的业务调查，并让旧 Plan 与审批失效；新调查 Run 会重新消费更正。</p>
            <textarea v-model="correctionDraft" data-testid="critical-correction-input" rows="3" maxlength="20000" placeholder="更正：请说明新核实的事实或应优先调查的线索。" :disabled="busy || !csrf"></textarea>
            <button class="outline-button" type="button" data-testid="submit-critical-correction" :disabled="!correctionDraft.trim() || busy || !csrf" @click="submitCriticalCorrection">提交关键更正</button>
          </div>
          <div class="inspector-section">
            <div class="section-heading"><h3>MCP 与模型轨迹</h3><span class="section-count">{{ inspector.observations.length + inspector.investigation_model_traces.length + inspector.chat_model_attempts.length }}</span></div>
            <div v-if="inspector.observations.length === 0 && inspector.investigation_model_traces.length === 0 && inspector.chat_model_attempts.length === 0" class="muted-card">尚无已记录的工具或模型调用。</div>
            <div v-for="item in inspector.observations.slice(0, 8)" :key="String(item.observation_id)" class="trace-row"><span class="trace-icon">⌕</span><span><strong>{{ String(item.tool_name) }}</strong><small>{{ String(item.status) }} · {{ dateLabel(item.created_at) }}</small></span><i class="status-dot" :class="statusTone(item.status)"></i></div>
            <div v-for="item in inspector.investigation_model_traces.slice(0, 4)" :key="String(item.provider_response_id ?? item.prompt_digest)" class="trace-row"><span class="trace-icon model-icon">✳</span><span><strong>{{ String(item.model_id) }}</strong><small>{{ String(item.status) }} · {{ JSON.stringify(item.usage) }}</small></span><i class="status-dot" :class="statusTone(item.status)"></i></div>
            <div v-for="item in inspector.chat_model_attempts.slice(0, 4)" :key="String(item.attempt_id)" class="trace-row"><span class="trace-icon model-icon">✳</span><span><strong>{{ String(item.model_id) }}</strong><small>Chat {{ String(item.status) }} · {{ item.total_tokens ?? 'Token 未提供' }} tokens</small></span><i class="status-dot" :class="statusTone(item.status)"></i></div>
          </div>
          <div class="inspector-section timeline-section"><div class="section-heading"><h3>事件时间线</h3><button class="text-button" type="button" @click="reconnectEvents">刷新</button></div>
            <div v-if="sessionEvents.length === 0" class="muted-card">持久事件到达后会显示在这里。</div>
            <div v-for="item in sessionEvents.slice(0, 12)" :key="item.event_seq" class="timeline-item"><span class="timeline-dot"></span><div><strong>{{ item.event_kind.replaceAll('_', ' ') }}</strong><small>{{ dateLabel(item.happened_at) }} · #{{ item.event_seq }}</small></div></div>
          </div>
        </template>
        <div v-else class="inspector-empty"><div class="inspector-empty-icon">◈</div><h3>等待关联 Task</h3><p>新建 S1 调查并输入真实故障描述后，这里会显示来源引用、可信 Evidence 和确定性 Gate。</p><button v-if="canCreateTask" class="outline-button" type="button" :disabled="!sessionId || busy || !csrf" @click="showTaskForm = true">新建调查任务</button></div>
        <footer class="inspector-footer"><span>OpsPilot vNext · M2-03</span><span>LOOPBACK ONLY</span></footer>
      </aside>
    </section>
  </main>
</template>
