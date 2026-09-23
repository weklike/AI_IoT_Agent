<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { poll } from '../polling'
import { stamp, type ChargingSession, type ChargingStatistics, type Page } from '../types'
const props = defineProps<{ deviceId: string }>()
const rows = ref<ChargingSession[]>([]), summary = ref<ChargingStatistics>(), cursor = ref<string | null>(null), error = ref(''), loading = ref(true), minutes = ref(30), historyPage = ref(false)
const lifetime = new AbortController()
let stop = () => {}, bounds = ''
function windowQuery() { const end = new Date(); return `device_id=${props.deviceId}&from=${encodeURIComponent(new Date(end.getTime() - minutes.value * 60000).toISOString())}&to=${encodeURIComponent(end.toISOString())}` }
async function load(signal: AbortSignal = lifetime.signal, more = false) {
  loading.value = true
  try {
    if (!more) bounds = windowQuery()
    const page = await api<Page<ChargingSession>>(`/charging-sessions?${bounds}&limit=20${more && cursor.value ? `&cursor=${encodeURIComponent(cursor.value)}` : ''}`, {}, signal)
    rows.value = more ? [...rows.value, ...page.items] : page.items; cursor.value = page.next_cursor
    if (!more) summary.value = await api<ChargingStatistics>(`/charging-statistics?${bounds}`, {}, signal)
    error.value = ''
  } catch (e) { if (!signal?.aborted) error.value = (e as Error).message }
  finally { if (!signal.aborted) loading.value = false }
}
function resume() { stop(); historyPage.value = false; stop = poll(signal => load(signal), 2000) }
async function more() { stop(); historyPage.value = true; await load(undefined, true) }
onMounted(resume); onUnmounted(() => { lifetime.abort(); stop() })
</script>
<template>
  <section class="panel" data-testid="session-list"><div class="section-title"><h2>充电会话与电量</h2><label>会话窗口<select v-model.number="minutes" @change="resume"><option :value="10">10 分钟</option><option :value="30">30 分钟</option><option :value="60">60 分钟</option></select></label></div>
    <p v-if="summary" class="notice">完整窗口 {{ summary.session_count }} 个会话 · 活动 {{ summary.active_count }} · 窗口内结束会话电量 {{ summary.completed_session_energy_wh ?? '—' }} Wh<span v-if="summary.missing_report_count"> · {{ summary.missing_report_count }} 个会话缺少设备报告</span></p>
    <p class="muted">电量由设备累计表底报告；这里汇总窗口内结束的会话，不等同于按时间精确切分的站点用电量。</p><p v-if="error" role="alert" class="alert">{{ error }}</p><p v-if="loading && !rows.length">正在加载会话…</p><p v-else-if="!rows.length" class="empty">该窗口暂无会话</p>
    <div class="table-scroll"><table v-if="rows.length" class="operations-table"><thead><tr><th>会话</th><th>状态</th><th>电量</th><th>报告与时间</th></tr></thead><tbody><tr v-for="row in rows" :key="row.session_id"><td><code>{{ row.session_id }}</code><small>请求 {{ row.requested_power_w }} W</small></td><td>{{ row.status }}</td><td>{{ row.energy_wh ?? '—' }} Wh<small>{{ row.meter_quality || '质量未报告' }}</small></td><td>{{ row.report_missing ? '等待设备报告' : stamp(row.observed_at) }}<small>开始 {{ stamp(row.started_at) }}<br>结束 {{ stamp(row.ended_at) }}</small></td></tr></tbody></table></div>
    <div class="form-row"><button v-if="cursor" :disabled="loading" @click="more">加载更早会话</button><button v-if="historyPage" @click="resume">返回实时会话</button></div>
  </section>
</template>
