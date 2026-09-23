<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { useMutation } from '../mutations'
import { poll } from '../polling'
import { commandLabels, planLabels, stamp, verificationLabels, type PowerPlan, type StationState } from '../types'
defineProps<{ station?: StationState }>()
const previewRequest = useMutation('power-preview'), executeRequest = useMutation('power-execute')
const budget = ref(30000), strategy = ref('equal'), priority = ref('CHG-001,CHG-002,CHG-003'), plan = ref<PowerPlan>(), queryError = ref(''), planId = ref(localStorage.getItem('charge-ops-v2-plan') || '')
let stop = () => {}
function observe() {
  stop()
  stop = poll(async signal => {
    try { plan.value = await api<PowerPlan>(`/power-plans/${planId.value}`, {}, signal); queryError.value = ''; if (plan.value.status !== 'EXECUTING') return false }
    catch (e) { if (!signal.aborted) queryError.value = (e as Error).message; return false }
  }, 1000)
}
async function preview() {
  const result = await previewRequest.execute<{ plan_id: string }>('/power-plans', { budget_w: budget.value, strategy: strategy.value, device_priority: strategy.value === 'priority' ? priority.value.split(',') : null })
  if (result) { planId.value = result.plan_id; localStorage.setItem('charge-ops-v2-plan', result.plan_id); observe() }
}
async function execute() { const result = await executeRequest.execute(`/power-plans/${planId.value}/execute`); if (result) observe() }
async function retryPreview() { const result = await previewRequest.retry<{ plan_id: string }>(); if (result) { planId.value = result.plan_id; localStorage.setItem('charge-ops-v2-plan', result.plan_id); observe() } }
onMounted(() => { if (planId.value) observe() })
onUnmounted(() => stop())
</script>
<template>
  <section class="panel"><div class="section-title"><div><p class="eyebrow">STATION POWER / 调度</p><h2>站点功率分配</h2></div><span class="pill">已确认预算 {{ station?.budget_w ?? '—' }} W</span></div>
    <div class="form-row"><label>站点预算（W）<input v-model.number="budget" type="number" min="0" max="60000" step="100" :disabled="previewRequest.busy.value || !!previewRequest.pending.value"></label><label>分配策略<select v-model="strategy" :disabled="previewRequest.busy.value || !!previewRequest.pending.value"><option value="equal">平均分配</option><option value="priority">按优先级分配</option></select></label><label v-if="strategy === 'priority'">设备优先级<select v-model="priority"><option value="CHG-001,CHG-002,CHG-003">001 → 002 → 003</option><option value="CHG-002,CHG-001,CHG-003">002 → 001 → 003</option><option value="CHG-003,CHG-002,CHG-001">003 → 002 → 001</option></select></label><button :disabled="previewRequest.busy.value || !!previewRequest.pending.value || plan?.status === 'EXECUTING'" @click="preview">生成预览</button></div>
    <div v-if="plan" data-testid="power-plan" class="operation-result"><div class="section-title"><strong>{{ planLabels[plan.status] || plan.status }}</strong><span class="muted">预览生成于 {{ stamp(plan.created_at) }} · 120 秒内有效</span></div><div class="allocation-grid"><div v-for="(watts, device) in plan.allocation_json" :key="device"><b>{{ device }}</b><strong>{{ watts }} W</strong><small v-if="plan.commands[device]">{{ commandLabels[plan.commands[device].status] }} · {{ verificationLabels[plan.commands[device].verification_status] }}</small><small v-else>{{ plan.status === 'PREVIEW' ? '尚未发送' : '无新命令确认；查看计划结果' }}</small></div></div><p class="muted">目标预算 {{ plan.budget_w }} W · 过渡保护预算 {{ plan.protection_budget_w }} W · 已确认预算 {{ plan.confirmed_budget_w }} W</p><p v-if="plan.status === 'PARTIAL'" class="alert">存在未确认结果，不能认定新预算已生效；不会自动重试或回滚。</p><button v-if="plan.status === 'PREVIEW'" class="primary" :disabled="executeRequest.busy.value" @click="execute">执行此计划</button><details v-if="plan.status !== 'PREVIEW'"><summary>逐设备执行结果</summary><pre>{{ JSON.stringify(plan.results_json, null, 2) }}</pre></details></div>
    <p v-if="previewRequest.error.value || executeRequest.error.value || queryError" role="alert" class="alert">{{ previewRequest.error.value || executeRequest.error.value || queryError }}</p><button v-if="previewRequest.pending.value" :disabled="previewRequest.busy.value" @click="retryPreview">重试原预览请求</button><button v-if="executeRequest.pending.value" :disabled="executeRequest.busy.value" @click="execute">重试原执行请求</button><button v-if="queryError && planId" @click="observe">重新查询计划</button>
    <p class="muted">预览不下发命令。执行时先确认全部降低，再进行提升；设备状态变化或预览过期需重新预览。</p>
  </section>
</template>
