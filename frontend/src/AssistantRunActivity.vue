<script setup lang="ts">
import type { RunActivity } from './api';

defineProps<{
  activities: RunActivity[];
  running?: boolean;
  formatTime: (timestamp: string) => string;
}>();

function activityLabel(item: RunActivity): string {
  const { stage, tool_name, duration_ms, activity_status, memory_count } = item.payload;
  const tool = tool_name ? ` · ${tool_name}` : '';
  const duration = typeof duration_ms === 'number' ? ` · ${duration_ms} ms` : '';
  const labels: Record<string, string> = {
    PREPARING_CONTEXT: '正在准备上下文', CONTEXT_COMPACTION: '正在压缩历史上下文',
    MEMORY_SELECTED: `已选择 ${memory_count ?? 0} 条有效个人记忆`,
    MODEL_REQUESTING: '等待模型响应', MODEL_RESPONSE_REPLAYING: '正在恢复已持久化的模型响应',
    MODEL_STREAMING: '模型正在生成', TOOL_RUNNING: `正在执行工具${tool}`,
    TOOL_COMPLETED: `${activity_status === 'SUCCEEDED' ? '工具已返回' : '工具执行失败'}${tool}${duration}`,
    SAVING_ANSWER: '正在保存最终回答',
  };
  return labels[stage] ?? stage;
}
</script>

<template>
  <details v-if="activities.length" class="assistant-run-activity" data-testid="assistant-run-activity">
    <summary>
      <span v-if="running" role="status">{{ activityLabel(activities[activities.length - 1]) }}</span>
      <span v-else>实际执行步骤</span>
    </summary>
    <ol>
      <li v-for="item in activities" :key="item.event_seq" :class="{ 'activity-failed': item.payload.activity_status === 'FAILED' }">
        <span>{{ activityLabel(item) }}</span><time :datetime="item.happened_at">{{ formatTime(item.happened_at) }}</time>
      </li>
    </ol>
  </details>
</template>
