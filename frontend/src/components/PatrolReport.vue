<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { api } from '../api'
import { poll } from '../polling'
import { connectionLabels, runLabels, stamp, type Patrol, type Run } from '../types'
import MarkdownAnswer from './MarkdownAnswer.vue'
import ToolTrace from './ToolTrace.vue'
import KnowledgeSources from './KnowledgeSources.vue'
const props = defineProps<{ reportId: string }>()
const report = ref<Patrol>(), run = ref<Run>(), error = ref('')
let stop = () => {}
function observe() {
  stop()
  stop = poll(async signal => {
    try { report.value = await api<Patrol>(`/patrols/${props.reportId}`, {}, signal); if (report.value.run_id) run.value = await api<Run>(`/agent/runs/${report.value.run_id}`, {}, signal); error.value = ''; if (!['queued','running'].includes(report.value.status)) return false }
    catch (e) { if (!signal.aborted) error.value = (e as Error).message; return false }
  }, 1000)
}
watch(() => props.reportId, () => { report.value = undefined; run.value = undefined; observe() }, { immediate: true })
onUnmounted(() => stop())
</script>
<template>
  <section class="panel patrol-report"><div class="section-title"><div><p class="eyebrow">PATROL REPORT / 证据报告</p><h2>巡检报告</h2></div><span class="pill" :class="{ offline: report && !['queued','running','completed'].includes(report.status) }">{{ report ? runLabels[report.status] || report.status : '正在获取' }}</span></div><p class="run-id">{{ reportId }}</p><p v-if="error" role="alert" class="alert">{{ error }} <button @click="observe">重试查询</button></p><p v-if="report && report.status !== 'completed' && !['queued','running'].includes(report.status)" class="alert">本次巡检未成功完成。以下仅保留已经获得的真实事实，不代表完整分析结论。</p>
    <template v-if="report?.snapshot_json"><h3>观测 · 工具事实</h3><p class="muted">窗口 {{ stamp(report.snapshot_json.from) }} 至 {{ stamp(report.snapshot_json.to) }} · 已确认站点预算 {{ report.snapshot_json.station.budget_w }} W</p><div class="patrol-facts"><article v-for="item in report.snapshot_json.devices" :key="item.device_id" :data-testid="`patrol-fact-${item.device_id}`"><div class="section-title"><b>{{ item.device_id }}</b><span class="pill">{{ connectionLabels[item.status.connection_state] }}</span></div><strong>{{ item.statistics.sample_count }} 条样本</strong><p>{{ item.status.data_fresh ? '数据新鲜' : '数据过期 / 未知' }} · 样本 {{ stamp(item.status.sample_ts) }}</p><p>窗口温度均值 {{ item.statistics.temperature_avg_c ?? '未知' }} °C · 最高 {{ item.statistics.temperature_max_c ?? '未知' }} °C</p><p>最后功率限制 {{ item.status.power_limit_w ?? '未知' }} W · 窗口结束会话电量 {{ item.charging_statistics.completed_session_energy_wh ?? '未知' }} Wh</p></article></div></template><p v-else-if="report" class="empty">尚未获得成功的站点事实快照。</p>
    <div v-if="run?.answer"><h3>可能原因与建议 · 模型说明</h3><small class="muted">{{ run.llm_mode === 'fixture' ? 'fixture 替身模型，仅验证工程流程' : 'real 真实模型；语义正确性另行验收' }}</small><MarkdownAnswer :content="run.answer" /></div>
  </section><KnowledgeSources v-if="run?.answer_refs" :references="run.answer_refs" /><ToolTrace v-if="run" :calls="run.tool_calls" :references="run.answer_refs || []" />
</template>
