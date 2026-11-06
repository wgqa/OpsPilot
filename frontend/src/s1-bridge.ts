import type { TaskOutcome } from './api';

/** Only S3 bindings are accepted by the Assistant's task-scoped message API. */
export function assistantTaskForSend(taskId: string, inspectedTask: Record<string, unknown> | null): string | null {
  return taskId && inspectedTask?.task_id === taskId && inspectedTask.service_id === 'orders-async-demo'
    ? taskId : null;
}

/** Present only persisted Domain results; a completed Run is not a recovery receipt. */
export function s1OutcomeText(outcome: TaskOutcome | null, taskStatus: string, runStatus: string): string {
  if (outcome?.business_outcome === 'DELIVERED' && outcome.verification?.recovery_verified === true)
    return '已通过在线业务验证并完成正式交付。';
  if (outcome?.business_outcome === 'RECOVERED_NOT_DELIVERED' && outcome.verification?.recovery_verified === true)
    return '已通过在线业务验证；正式交付尚未完成。';
  if (outcome?.business_outcome === 'REJECTED') return '该方案审批已拒绝；尚未确认业务恢复。';
  if (['FAILED', 'BLOCKED', 'ABORTED', 'EXPIRED'].includes(taskStatus) || ['FAILED', 'BLOCKED'].includes(runStatus))
    return '调查未能完成或已失效，未确认业务恢复。';
  if (outcome?.business_outcome === 'WAITING_APPROVAL' && outcome.plan?.eligibility === 'ACTIVE' && taskStatus === 'WAITING_APPROVAL')
    return '已形成受控方案，等待独立审批；尚未修复。';
  if (taskStatus === 'WAITING_APPROVAL') return '审批状态无法与可信方案核对；尚未修复。';
  if (outcome?.business_outcome === 'APPROVAL_ACCEPTED') return '已记录审批，尚未确认业务恢复。';
  if (runStatus === 'SUCCEEDED') return '调查运行已结束；尚未确认业务恢复。';
  return '调查正在进行或等待处理；尚未确认业务恢复。';
}
