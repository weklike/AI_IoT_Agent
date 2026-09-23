<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { useMutation } from '../mutations'
import { poll } from '../polling'
import { runLabels, stamp, type Page, type Patrol, type PatrolSchedule } from '../types'
const operation = useMutation('patrol'), scheduleChange = useMutation('patrol-schedule')
const windowMinutes = ref(30), report = ref<Patrol>(), recent = ref<Patrol[]>([]), schedule = ref<PatrolSchedule>(), error = ref('')
const selectedId = ref(localStorage.getItem('charge-ops-v2-patrol') || '')
const running = computed(() => !!selectedId.value && (!report.value || report.value.report_id !== selectedId.value || ['queued','running'].includes(report.value.status)))
let stop = () => {}, stopReport = () => {}
function observe() {
  stopReport()
  stopReport = poll(async signal => {
    try { report.value = await api<Patrol>(`/patrols/${selectedId.value}`, {}, signal); error.value = ''; if (!['queued','running'].includes(report.value.status)) return false }
    catch (e) { if (!signal.aborted) error.value = (e as Error).message; return false }
  }, 1000)
}
function select(id: string) { selectedId.value = id; localStorage.setItem('charge-ops-v2-patrol', id); observe() }
async function start() { const result = await operation.execute<{ report_id: string }>('/patrols', { window_minutes: windowMinutes.value }); if (result) select(result.report_id) }
async function retry() { const result = await operation.retry<{ report_id: string }>(); if (result) select(result.report_id) }
async function toggle() { if (scheduleChange.pending.value) { const restored = await scheduleChange.retry<PatrolSchedule>(); if (restored) schedule.value = restored; return }; if (!schedule.value) return; const result = await scheduleChange.execute<PatrolSchedule>('/patrol-schedule', { expected_version: schedule.value.version, enabled: !schedule.value.enabled }, 'PUT'); if (result) schedule.value = result }
onMounted(() => {
  if (selectedId.value) observe()
  stop = poll(async signal => {
    try { const [list, config] = await Promise.all([api<Page<Patrol>>('/patrols?limit=5', {}, signal), api<PatrolSchedule>('/patrol-schedule', {}, signal)]); recent.value = list.items; schedule.value = config; if (!selectedId.value && list.items[0]) select(list.items[0].report_id) }
    catch (e) { if (!signal.aborted) error.value = (e as Error).message }
  }, 2000)
})
onUnmounted(() => { stop(); stopReport() })
</script>
<template>
  <section class="panel"><div class="section-title"><div><p class="eyebrow">FLEET PATROL / 只读巡检</p><h2>站点巡检</h2></div><span class="pill">与聊天共享一个运行槽位</span></div>
    <div class="form-row"><label>巡检窗口<select v-model.number="windowMinutes" :disabled="running || operation.busy.value || !!operation.pending.value"><option :value="10">10 分钟</option><option :value="30">30 分钟</option><option :value="60">60 分钟</option></select></label><button class="primary" :disabled="running || operation.busy.value || !!operation.pending.value" @click="start">一键巡检</button><button v-if="operation.pending.value" :disabled="operation.busy.value" @click="retry">重试原巡检请求</button></div>
    <p class="muted">查询三台设备并保存实际观测。巡检不建单、不控制设备；模型失败也会保留已获得的事实。</p>
    <div v-if="selectedId" class="operation-result" data-testid="patrol-summary"><strong>{{ report?.report_id === selectedId ? runLabels[report.status] || (report.status === 'skipped_busy' ? '忙碌跳过，未执行' : report.status) : '正在获取巡检报告' }}</strong><p class="run-id">{{ selectedId }}</p><p v-if="report">{{ stamp(report.created_at) }} · {{ report.window_minutes }} 分钟窗口 · {{ report.trigger === 'manual' ? '手动' : '定时' }}触发</p><RouterLink :to="`/agent?report=${selectedId}`" class="text-link" aria-label="查看巡检报告">查看巡检报告 →</RouterLink><button v-if="error" @click="observe">重新查询报告</button></div>
    <div v-if="schedule" class="schedule-row"><div><b>{{ schedule.enabled ? '定时巡检已启用' : '定时巡检已关闭' }}</b><small>启用后每 30 分钟巡检最近 30 分钟；忙碌跳过，不补跑。<span v-if="schedule.next_due_at">下次 {{ stamp(schedule.next_due_at) }}</span></small></div><button :disabled="scheduleChange.busy.value" @click="toggle">{{ scheduleChange.pending.value ? '重试原计划设置' : schedule.enabled ? '关闭定时巡检' : '启用定时巡检' }}</button></div>
    <p v-if="error || operation.error.value || scheduleChange.error.value" role="alert" class="alert">{{ error || operation.error.value || scheduleChange.error.value }}</p>
    <details v-if="recent.length"><summary>最近 {{ recent.length }} 份报告</summary><ul class="compact-list"><li v-for="item in recent" :key="item.report_id"><button @click="select(item.report_id)">{{ stamp(item.created_at) }} · {{ runLabels[item.status] || item.status }}</button></li></ul></details>
  </section>
</template>
