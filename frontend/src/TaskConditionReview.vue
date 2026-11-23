<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { api, explainError, type ConditionCandidate, type ConditionReviewState } from './api';

const props = defineProps<{ taskId: string; sourceId: string; csrf: string; busy: boolean; revision: string }>();
const emit = defineEmits<{ accepted: [runId: string]; edit: [text: string] }>();
const data = ref<ConditionReviewState>({ active: [], review: null });
const shown = ref(false);
const working = ref(false);
const selected = ref<string[]>([]);
const message = ref('');
const review = computed(() => data.value.review);
let current = 0;

const actions = { ADD: '新增', REPLACE: '替换', REVOKE: '撤回', ACTIVE: '已生效',
  CONFLICT: '有冲突', HYPOTHESIS: '假设', QUOTE: '引用', UNCERTAIN: '待核实' };
const slots: Record<string, string> = { event: '事件', protocol: '协议', time: '时间范围', report: '报告格式' };
const reviewStatus: Record<string, string> = {
  ASSESSING: '正在核对，尚未收到结果',
  PENDING_CONFIRMATION: '等待你选择和确认',
  CONFIRMED: '已确认，待新一轮调查应用',
  STALE: '消息或任务版本已变化，请重新核对',
  NO_UPDATE: '没有可直接确认的变更',
  FAILED: '本次核对未完成',
  CANCELLED: '已放弃本次核对',
};

function update(state: ConditionReviewState): void {
  if (state.review?.id !== review.value?.id || state.review?.status !== 'PENDING_CONFIRMATION') selected.value = [];
  data.value = state;
}

async function refresh(restore = false): Promise<void> {
  if (working.value) return;
  const generation = ++current;
  try {
    const state = await api.conditionReview(props.taskId);
    if (generation !== current) return;
    update(state);
    if (restore && (state.review?.status === 'PENDING_CONFIRMATION' || state.review?.status === 'CONFIRMED')) shown.value = true;
  } catch (error) {
    if (generation !== current) return;
    data.value = { active: [], review: null };
    message.value = explainError(error);
  }
}

async function discover(): Promise<void> {
  if (!props.sourceId || working.value) return;
  const generation = ++current;
  working.value = true;
  message.value = '';
  try {
    const state = await api.discoverConditions(props.taskId, props.sourceId, props.csrf);
    if (generation === current) update(state);
  } catch (error) {
    if (generation === current) message.value = explainError(error);
  } finally {
    working.value = false;
  }
}

function selectable(item: ConditionCandidate): boolean {
  return review.value?.status === 'PENDING_CONFIRMATION' && item.source_text !== null
    && ['ADD', 'REPLACE', 'REVOKE'].includes(item.action);
}

async function confirm(): Promise<void> {
  const pending = review.value;
  if (!pending || !selected.value.length || working.value) return;
  const generation = ++current;
  working.value = true;
  message.value = '';
  try {
    const receipt = await api.confirmConditions(props.taskId, pending, selected.value, props.csrf);
    if (generation === current) emit('accepted', receipt.run_id);
  } catch (error) {
    if (generation === current) message.value = explainError(error);
  } finally {
    working.value = false;
    if (generation === current) await refresh();
  }
}

async function cancel(): Promise<void> {
  const pending = review.value;
  if (!pending || working.value) return;
  const generation = ++current;
  working.value = true;
  message.value = '';
  try {
    const state = await api.cancelConditions(props.taskId, pending, props.csrf);
    if (generation === current) update(state);
  } catch (error) {
    if (generation === current) message.value = explainError(error);
  } finally {
    working.value = false;
  }
}

onMounted(() => void refresh(true));
watch(() => [props.sourceId, props.revision], () => void refresh());
onBeforeUnmount(() => { current += 1; });
</script>

<template>
  <div class="task-condition-review">
    <button type="button" class="text-button" data-testid="condition-review-toggle" :aria-expanded="shown"
      @click="shown = !shown; if (shown) refresh()">任务条件<span v-if="data.active.length"> · {{ data.active.length }} 项生效</span></button>
    <section v-if="shown" class="update-proposal-card condition-review-card" aria-label="任务条件审核" data-testid="condition-review">
      <div class="update-proposal-heading">
        <h2>任务条件</h2>
        <button type="button" class="outline-button" data-testid="condition-review-discover"
          :disabled="working || busy || !csrf || !sourceId || review?.source_message_id === sourceId" @click="discover">
          {{ working ? '处理中…' : '从对话核对条件' }}
        </button>
      </div>
      <p>确认后用于后续调查。一次性要求可直接在对话中说明。</p>
      <p v-if="message" role="status">{{ message }}</p>
      <ul v-if="data.active.length" class="condition-list" aria-label="当前生效条件">
        <li v-for="item in data.active" :key="item.slot"><strong>{{ slots[item.slot] ?? '调查条件' }}</strong> {{ item.text }} <small>第 {{ item.sequence }} 条消息</small></li>
      </ul>
      <template v-if="review">
        <p role="status" data-testid="condition-review-status">
          {{ review.application_state === 'APPLIED_TO_RUN' ? '已应用到后续调查' : reviewStatus[review.status] ?? review.status }}
          <button v-if="review.status === 'ASSESSING' || (review.status === 'CONFIRMED' && review.application_state !== 'APPLIED_TO_RUN')" class="text-button" type="button" @click="refresh()">查看最新状态</button>
        </p>
        <p v-if="review.reason === 'TASK_AUX_PROVIDER_LIMIT'">当前任务的模型调用额度已用尽。请核对或重新说明必要条件。</p>
        <p v-else-if="review.status === 'FAILED'">暂时无法恢复候选。可重新说明要求后再核对。</p>
        <p v-if="review.partial" data-testid="condition-review-partial">
          核对范围不完整。已读取 {{ review.coverage.messages_read }} 条消息，其中 {{ review.coverage.excerpted }} 条仅查看片段。请检查遗漏或补充来源。
        </p>
        <ul v-if="review.candidates.length" class="condition-list">
          <li v-for="item in review.candidates" :key="item.id" data-testid="condition-candidate">
            <label>
              <input v-if="selectable(item)" v-model="selected" type="checkbox" :value="item.id" :disabled="working || busy" />
              <strong>{{ actions[item.action] }} · {{ slots[item.slot] ?? '调查条件' }}</strong>
            </label>
            <small v-if="item.current_text">当前条件：{{ item.current_text }}</small>
            <blockquote v-if="item.source_text">{{ item.source_text }} <small>第 {{ item.sequence }} 条消息</small></blockquote>
            <small v-else>来源已不可用</small>
            <button v-if="item.action === 'CONFLICT' || item.action === 'UNCERTAIN'" class="text-button" type="button"
              :disabled="!item.source_text || busy" @click="item.source_text && emit('edit', item.source_text)">修改为新消息</button>
          </li>
        </ul>
        <div v-if="review.status === 'PENDING_CONFIRMATION' || (review.status === 'NO_UPDATE' && review.candidates.length)" class="update-proposal-actions">
          <small v-if="review.status === 'PENDING_CONFIRMATION'">跳过不采纳的条目。确认所选项将启动新一轮调查。</small>
          <button class="text-button" type="button" :disabled="working || busy || !csrf" @click="cancel">放弃本次核对</button>
          <button v-if="review.status === 'PENDING_CONFIRMATION'" class="primary-button" type="button" data-testid="condition-review-confirm"
            :disabled="!selected.length || working || busy || !csrf" @click="confirm">确认所选条件</button>
        </div>
      </template>
    </section>
  </div>
</template>
