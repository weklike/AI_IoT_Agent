<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, post } from '../api'
import { poll } from '../polling'
import { connectionLabels, healthLabels, stamp, metric, type Device, type Sample, type Command, type WorkOrder } from '../types'
import TelemetryChart from '../components/TelemetryChart.vue'
import WorkOrders from '../components/WorkOrders.vue'
const id = String(useRoute().params.id)
const device = ref<Device>(), samples = ref<Sample[]>([]), orders = ref<WorkOrder[]>([])
const error = ref(''), commandError = ref(''), command = ref<Command>(), windowMinutes = ref(10), sending = ref(false), loading = ref(true)
let stop = () => {}, stopCommand = () => {}, disposed = false
const commandAbort = new AbortController()
onMounted(() => { stop = poll(async signal => {
  try {
    const end = new Date(), start = new Date(end.getTime() - windowMinutes.value * 60000)
    const data = await Promise.all([api<Device>(`/devices/${id}`, {}, signal),
      api<Sample[]>(`/devices/${id}/telemetry?from=${encodeURIComponent(start.toISOString())}&to=${encodeURIComponent(end.toISOString())}`, {}, signal),
      api<WorkOrder[]>(`/work-orders?device_id=${id}`, {}, signal)])
    ;[device.value, samples.value, orders.value] = data; error.value = ''
  } catch (e) { if (!signal.aborted) error.value = (e as Error).message }
  finally { loading.value = false }
}, 2000) })
onUnmounted(() => { disposed = true; commandAbort.abort(); stop(); stopCommand() })
async function changeScenario(scenario: string) {
  if (sending.value) return
  sending.value = true; commandError.value = ''; stopCommand()
  try {
    command.value = { ...await post<Command>('/simulator/scenarios', { device_id: id, scenario }, commandAbort.signal), scenario }
    if (disposed) return
    const commandId = command.value.command_id
    stopCommand = poll(async signal => {
      try {
        command.value = await api<Command>(`/simulator/commands/${commandId}`, {}, signal)
        if (command.value.status !== 'pending') { sending.value = false; return false }
      } catch (e) { if (!signal.aborted) { commandError.value = (e as Error).message; sending.value = false }; return false }
    }, 1000)
  } catch (e) { if (!disposed) commandError.value = (e as Error).message; sending.value = false }
}
</script>
<template>
  <RouterLink class="back" to="/devices">← 返回设备总览</RouterLink>
  <div class="page-heading"><div><p class="eyebrow">DEVICE INSIGHT / 01</p><h1>{{ id }}</h1><p class="muted">当前指标、遥测历史与场景控制</p></div><span v-if="device" class="pill" :class="device.connection_state" data-testid="device-connection">{{ connectionLabels[device.connection_state] }}</span></div>
  <div v-if="error" role="alert" class="alert">{{ error }}；请确认连接和设备 ID。</div><p v-if="loading">正在加载设备…</p>
  <template v-if="device">
    <section class="detail-metrics"><div><small>温度</small><strong>{{ metric(device.temperature_c, '°C') }}</strong></div><div><small>功率</small><strong>{{ metric(device.power_kw, 'kW') }}</strong></div><div><small>电压 / 电流</small><strong class="smaller">{{ metric(device.voltage_v, 'V') }} / {{ metric(device.current_a, 'A') }}</strong></div><div><small>健康状态</small><b data-testid="device-health" :class="device.health_state">{{ healthLabels[device.health_state] }}</b><span>{{ device.data_fresh ? '数据新鲜' : '数据过期 / 未知' }}</span></div></section>
    <p class="sample-time">最后样本 {{ stamp(device.sample_ts) }} · 数据年龄 {{ device.data_age_seconds === null ? '未知' : `${device.data_age_seconds.toFixed(1)} 秒` }}</p>
    <section class="panel"><div class="section-title"><h2>温度历史</h2><label>时间窗口 <select v-model="windowMinutes" aria-label="历史窗口"><option :value="10">10 分钟</option><option :value="30">30 分钟</option><option :value="60">60 分钟</option></select></label></div><TelemetryChart v-if="samples.length" :samples="samples" /><p v-else class="empty">该窗口暂无历史样本</p></section>
    <section class="panel"><div class="section-title"><div><h2>模拟场景</h2><p class="muted">命令收到匹配回执后才确认应用；不是实际电路控制。</p></div><div class="button-group"><button :disabled="sending" @click="changeScenario('normal')">恢复正常</button><button :disabled="sending" @click="changeScenario('overheat')">模拟过温</button><button :disabled="sending" @click="changeScenario('offline')">暂停上报</button></div></div>
      <p v-if="command" data-testid="command-status" :class="{ orange: command.status === 'timed_out' }">{{ { pending: '等待设备回执…', applied: '已应用', rejected: '命令被拒绝', timed_out: '回执超时，执行结果未确认。请查看新鲜遥测或发送新命令。' }[command.status] }}<span v-if="command.status === 'applied' && command.scenario === 'offline'"> · 已暂停上报，等待离线判定</span></p><p v-if="commandError" role="alert" class="alert">{{ commandError }}</p>
    </section><WorkOrders :orders="orders" />
  </template>
</template>
