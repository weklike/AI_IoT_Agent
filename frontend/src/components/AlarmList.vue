<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { useMutation } from '../mutations'
import { poll } from '../polling'
import { stamp, type Alarm, type Page } from '../types'
const props = defineProps<{ deviceId?: string }>()
const operation = useMutation(`alarm-ack:${props.deviceId || 'station'}`)
const device = ref(props.deviceId || ''), condition = ref('ACTIVE'), reason = ref(''), acknowledged = ref('')
const rows = ref<Alarm[]>([]), cursor = ref<string | null>(null), error = ref(''), loading = ref(true), browsing = ref(false)
const lifetime = new AbortController()
let stop = () => {}
async function load(signal: AbortSignal = lifetime.signal, more = false) {
  loading.value = true
  try {
    const query = new URLSearchParams({ limit: '20' })
    if (device.value) query.set('device_id', device.value)
    if (condition.value) query.set('condition', condition.value)
    if (reason.value) query.set('reason', reason.value)
    if (acknowledged.value) query.set('acknowledged', acknowledged.value)
    if (more && cursor.value) query.set('cursor', cursor.value)
    const page = await api<Page<Alarm>>(`/alarms?${query}`, {}, signal)
    rows.value = more ? [...rows.value, ...page.items] : page.items; cursor.value = page.next_cursor; error.value = ''
  } catch (e) { if (!signal.aborted) error.value = (e as Error).message }
  finally { if (!signal.aborted) loading.value = false }
}
function resume() { stop(); browsing.value = false; stop = poll(signal => load(signal), 2000) }
async function more() { stop(); browsing.value = true; await load(lifetime.signal, true) }
async function acknowledge(alarm: Alarm) { const result = await operation.execute(`/alarms/${alarm.alarm_id}/acknowledge`, { expected_version: alarm.version }); if (result) resume() }
async function retry() { if (await operation.retry()) resume() }
onMounted(resume); onUnmounted(() => { stop(); lifetime.abort() })
</script>
<template>
  <section class="panel" data-testid="alarm-list"><div class="section-title"><div><p class="eyebrow">ALARMS / 状态与确认</p><h2>告警事件</h2></div><span class="muted">确认已知晓不代表故障已恢复</span></div>
    <div class="form-row"><label v-if="!deviceId">告警设备<select v-model="device" @change="resume"><option value="">全部设备</option><option>CHG-001</option><option>CHG-002</option><option>CHG-003</option></select></label><label>告警状态<select v-model="condition" @change="resume"><option value="ACTIVE">活动告警</option><option value="CLEARED">已恢复</option><option value="">全部状态</option></select></label><label>告警原因<select v-model="reason" @change="resume"><option value="">全部原因</option><option value="OVERHEAT">过温</option><option value="OFFLINE">离线</option></select></label><label>确认状态<select v-model="acknowledged" @change="resume"><option value="">全部</option><option value="false">未确认</option><option value="true">已确认</option></select></label></div>
    <p v-if="loading && !rows.length">正在加载告警…</p><p v-else-if="!rows.length && !error" class="empty">当前筛选下暂无告警</p><p v-if="error || operation.error.value" role="alert" class="alert">{{ error || operation.error.value }}</p>
    <article v-for="alarm in rows" :key="alarm.alarm_id" class="alarm-row"><div><b>{{ alarm.device_id }} · {{ alarm.reason_code }}</b><p><span class="pill" :class="{ offline: alarm.condition === 'ACTIVE' }">{{ alarm.condition }}</span> · {{ alarm.acknowledged_at ? '已确认' : '未确认' }} · {{ alarm.evaluation_state === 'unknown' ? '当前判断未知，告警尚未自动清除' : alarm.evaluation_state }}</p><small>发现 {{ stamp(alarm.started_at) }}<span v-if="alarm.cleared_at"> · 恢复 {{ stamp(alarm.cleared_at) }}</span></small></div><button v-if="!alarm.acknowledged_at" :disabled="operation.busy.value || !!operation.pending.value" @click="acknowledge(alarm)">确认已知晓</button></article>
    <div class="form-row"><button v-if="operation.pending.value" :disabled="operation.busy.value" @click="retry">重试原确认请求</button><button v-if="cursor" :disabled="loading" @click="more">加载更早告警</button><button v-if="browsing" @click="resume">返回实时告警</button></div>
  </section>
</template>
