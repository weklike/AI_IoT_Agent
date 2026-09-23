<script setup lang="ts">
import { onUnmounted, ref } from 'vue'
import { api } from '../api'
import { useMutation } from '../mutations'
import { stamp, type Page, type WorkOrder, type WorkOrderEvent } from '../types'
const props = defineProps<{ order: WorkOrder }>()
const emit = defineEmits<{ changed: [value: Partial<WorkOrder>] }>()
const operation = useMutation(`order:${props.order.order_id}`), lifetime = new AbortController()
const note = ref(''), events = ref<WorkOrderEvent[]>([]), cursor = ref<string | null>(null), opened = ref(false), error = ref(''), loading = ref(false)
async function transition(target: string) { const result = await operation.execute<Partial<WorkOrder>>(`/work-orders/${props.order.order_id}/transitions`, { expected_version: props.order.version, target_status: target, note: note.value }); if (result) { emit('changed', result); if (opened.value) await loadEvents() } }
async function retry() { const result = await operation.retry<Partial<WorkOrder>>(); if (result) { emit('changed', result); if (opened.value) await loadEvents() } }
async function loadEvents(more = false) {
  if (loading.value) return
  loading.value = true; opened.value = true
  try { const page = await api<Page<WorkOrderEvent>>(`/work-orders/${props.order.order_id}/events?limit=20${more && cursor.value ? `&cursor=${cursor.value}` : ''}`, {}, lifetime.signal); events.value = more ? [...events.value, ...page.items] : page.items; cursor.value = page.next_cursor; error.value = '' }
  catch (e) { if (!lifetime.signal.aborted) error.value = (e as Error).message }
  finally { loading.value = false }
}
onUnmounted(() => lifetime.abort())
</script>
<template>
  <article class="work-order-item" :data-testid="`work-order-${order.order_id}`"><div class="section-title"><b>{{ order.device_id }} · {{ order.reason_code }}</b><span class="pill">{{ order.status }} · v{{ order.version }}</span></div><code class="run-id">{{ order.order_id }}</code><p class="muted">创建 {{ stamp(order.created_at) }}<span v-if="order.closed_at"> · 关闭 {{ stamp(order.closed_at) }}</span><span v-if="order.alarm_id"> · 已关联告警</span></p>
    <label v-if="order.status !== 'CLOSED'" class="note-label">处理说明<textarea v-model="note" rows="2" maxlength="2000" :disabled="operation.busy.value || !!operation.pending.value" placeholder="记录具体处理动作；标记已解决时必填"></textarea></label><div class="form-row"><button v-if="order.status === 'OPEN'" :disabled="operation.busy.value || !!operation.pending.value" @click="transition('IN_PROGRESS')">开始处理</button><button v-if="order.status === 'IN_PROGRESS'" :disabled="operation.busy.value || !!operation.pending.value || !note.trim()" @click="transition('RESOLVED')">标记已解决</button><template v-if="order.status === 'RESOLVED'"><button class="primary" :disabled="operation.busy.value || !!operation.pending.value" @click="transition('CLOSED')">验证恢复并关闭</button><button :disabled="operation.busy.value || !!operation.pending.value" @click="transition('IN_PROGRESS')">重新处理</button></template><button :disabled="loading" @click="loadEvents()">查看处理记录</button><button v-if="operation.pending.value" :disabled="operation.busy.value" @click="retry">重试原工单请求</button></div>
    <p v-if="operation.error.value || error" role="alert" class="alert">{{ operation.error.value || error }}</p><p v-if="order.status === 'RESOLVED'" class="muted">关闭需要新鲜恢复样本，且关联告警已经恢复；由服务器重新核验。</p><div v-if="opened" class="event-history"><p v-if="!events.length && !loading" class="muted">暂无处理记录。</p><div v-for="event in events" :key="event.event_id"><p><b>{{ event.from_status }} → {{ event.to_status }}</b> · {{ stamp(event.checked_at) }}</p><p>{{ event.note || '无附加说明' }}</p><details v-if="Object.keys(event.evidence_json).length"><summary>恢复证据 · 原始样本与校验时间</summary><pre>{{ JSON.stringify(event.evidence_json, null, 2) }}</pre></details></div><button v-if="cursor" :disabled="loading" @click="loadEvents(true)">加载更早处理记录</button></div>
  </article>
</template>
