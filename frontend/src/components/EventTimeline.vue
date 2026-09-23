<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { poll } from '../polling'
import { eventLabels, stamp, type Timeline, type TimelineEvent } from '../types'
const props = defineProps<{ deviceId: string }>()
const emit = defineEmits<{ locate: [at: string] }>()
const events = ref<TimelineEvent[]>([]), count = ref(0), cursor = ref<string | null>(null), error = ref(''), loading = ref(false), replay = ref(false), minutes = ref(30)
const until = ref('')
const lifetime = new AbortController()
let stop = () => {}, bounds = ''
async function load(signal: AbortSignal = lifetime.signal, more = false) {
  loading.value = true
  try {
    if (!more) { const end = replay.value && until.value ? new Date(until.value) : new Date(); bounds = `from=${encodeURIComponent(new Date(end.getTime()-minutes.value*60000).toISOString())}&to=${encodeURIComponent(end.toISOString())}` }
    const result = await api<Timeline>(`/devices/${props.deviceId}/timeline?${bounds}&limit=100${more && cursor.value ? `&cursor=${encodeURIComponent(cursor.value)}` : ''}`, {}, signal)
    events.value = more ? [...result.items, ...events.value] : result.items; count.value = result.event_count; cursor.value = result.next_cursor; error.value = ''
  } catch (e) { if (!signal?.aborted) error.value = (e as Error).message }
  finally { if (!signal.aborted) loading.value = false }
}
function live() { stop(); replay.value = false; stop = poll(signal => load(signal), 2000) }
async function history() { stop(); replay.value = true; await load() }
async function more() { stop(); replay.value = true; await load(undefined, true) }
onMounted(live); onUnmounted(() => { lifetime.abort(); stop() })
</script>
<template>
  <section class="panel" data-testid="event-timeline"><div class="section-title"><div><p class="eyebrow">EVENT REPLAY / 事件复盘</p><h2>设备时间线</h2></div><span class="pill">{{ replay ? '历史只读' : '实时窗口' }} · {{ count }} 个事件</span></div>
    <div class="form-row"><label>事件窗口<select v-model.number="minutes" @change="replay ? history() : live()"><option :value="10">10 分钟</option><option :value="30">30 分钟</option><option :value="60">60 分钟</option><option :value="1440">24 小时</option></select></label><label>回放截止时间<input v-model="until" type="datetime-local"></label><button :disabled="loading || !until" @click="history">浏览历史窗口</button><button v-if="replay" @click="live">返回实时窗口</button></div>
    <p class="muted">回放只读取历史，不重发消息、不刷新在线状态、不触发告警或工单。完整计数 {{ count }}；当前展示 {{ events.length }} 条。</p><p v-if="error" role="alert" class="alert">{{ error }}</p><p v-if="!events.length && !loading" class="empty">该窗口暂无事件</p>
    <ol class="event-list"><li v-for="item in events" :key="`${item.source_type}:${item.source_id}`"><span class="event-dot" aria-hidden="true"></span><div><b>{{ eventLabels[item.source_type] || item.source_type }}</b><small>{{ stamp(item.observed_at) }}<span v-if="item.late_received"> · 晚到，接收于 {{ stamp(item.received_at) }}</span><span v-else-if="!item.received_at"> · 接收时间未记录</span></small><details><summary>查看实际来源 <code>{{ item.source_id }}</code></summary><pre>{{ JSON.stringify(item.detail, null, 2) }}</pre><button @click="emit('locate', item.observed_at)">定位关联曲线</button></details></div></li></ol><button v-if="cursor" :disabled="loading" @click="more">加载更早事件</button>
  </section>
</template>
