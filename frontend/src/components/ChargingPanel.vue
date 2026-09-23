<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { useMutation } from '../mutations'
import { poll } from '../polling'
import { commandLabels, verificationLabels, type Device, type DeviceCommand } from '../types'
const props = defineProps<{ device: Device }>()
const operation = useMutation(`charging:${props.device.device_id}`)
const watts = ref(10000), command = ref<DeviceCommand>(), queryError = ref(''), commandId = ref(''), acceptedSession = ref<string | null>(null)
const storageKey = `charge-ops-v2-charging:${props.device.device_id}`
const activeId = computed(() => props.device.session_id || acceptedSession.value)
const unsettled = computed(() => !!commandId.value && (!command.value || command.value.status === 'pending' || (command.value.status === 'applied' && command.value.verification_status === 'pending')))
let stop = () => {}
function persist() { localStorage.setItem(storageKey, JSON.stringify({ command_id: commandId.value, session_id: acceptedSession.value })) }
function observe() {
  stop()
  stop = poll(async signal => {
    try {
      command.value = await api<DeviceCommand>(`/device-commands/${commandId.value}`, {}, signal); queryError.value = ''
      if ((command.value.action === 'stop_session' && command.value.verification_status === 'verified') || (command.value.action === 'start_session' && command.value.status === 'rejected')) { acceptedSession.value = null; persist() }
      if (command.value.status !== 'pending' && (command.value.status !== 'applied' || command.value.verification_status !== 'pending')) return false
    } catch (e) { if (!signal.aborted) queryError.value = (e as Error).message; return false }
  }, 1000)
}
async function apply(action: 'start' | 'stop') {
  const result = await operation.execute<{ command_id: string; session_id: string }>(`/devices/${props.device.device_id}/charging/${action}`, action === 'start' ? { requested_power_w: watts.value } : { session_id: activeId.value })
  if (result) { acceptedSession.value = result.session_id; commandId.value = result.command_id; command.value = undefined; persist(); observe() }
}
async function retry() {
  const result = await operation.retry<{ command_id: string; session_id: string }>()
  if (result) { acceptedSession.value = result.session_id; commandId.value = result.command_id; command.value = undefined; persist(); observe() }
}
onMounted(() => {
  try { const saved = JSON.parse(localStorage.getItem(storageKey) || 'null'); if (saved?.command_id) { commandId.value = saved.command_id; acceptedSession.value = saved.session_id; observe() } } catch { queryError.value = '无法恢复控制记录。' }
})
onUnmounted(() => stop())
</script>
<template>
  <section class="panel" data-testid="charging-runtime">
    <div class="section-title"><div><p class="eyebrow">CHARGING / 运行</p><h2>充电运行</h2></div><span class="pill">{{ device.session_state || '未提供会话数据' }}</span></div>
    <div class="operations-metrics"><div><small>请求功率</small><strong>{{ device.requested_power_w ?? '—' }} W</strong></div><div><small>当前限制 · 最后样本</small><strong>{{ device.power_limit_w ?? '—' }} W</strong></div><div><small>本次电量</small><strong>{{ device.session_energy_wh ?? '—' }} Wh</strong></div><div><small>累计表底</small><strong>{{ device.meter_total_wh ?? '—' }} Wh</strong></div></div>
    <p v-if="device.session_state === 'ACTIVE' && device.power_limit_w === 0" class="notice">会话已开始，等待功率分配。初始限制为 0 W；请在设备总览预览并执行站点功率计划。</p>
    <p v-if="!device.data_fresh" class="muted">当前指标为最后记录，不能据此确认实时功率。已知会话仍可请求停止。</p>
    <div class="form-row"><label>请求功率（W）<input v-model.number="watts" type="number" min="100" max="20000" step="100" :disabled="operation.busy.value || !!operation.pending.value"></label><button class="primary" :disabled="operation.busy.value || !!operation.pending.value || unsettled || !device.data_fresh || device.schema_version !== 2 || device.session_state !== 'IDLE' || !!device.session_id" @click="apply('start')">开始充电</button><button :disabled="operation.busy.value || !!operation.pending.value || unsettled || !activeId" @click="apply('stop')">停止充电</button></div>
    <p v-if="commandId" data-testid="charging-command" class="notice">{{ command ? commandLabels[command.status] || command.status : '正在查询命令' }} · {{ command ? verificationLabels[command.verification_status] || command.verification_status : '' }}<span v-if="command?.error_code"> · {{ command.error_code }}</span></p>
    <p v-if="operation.error.value || queryError" role="alert" class="alert">{{ operation.error.value || queryError }}</p>
    <button v-if="operation.pending.value" :disabled="operation.busy.value" @click="retry">重试原充电请求</button><button v-if="queryError && commandId" @click="observe">重新查询命令</button>
    <p class="muted">收到设备回执与效果已验证分别显示。开始充电不会自动分配功率。</p>
  </section>
</template>
