<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { poll } from '../polling'
import { connectionLabels, healthLabels, metric, stamp, type Device } from '../types'
const devices = ref<Device[]>([]), error = ref(''), loading = ref(true)
const online = computed(() => devices.value.filter(d => d.connection_state === 'online').length)
const hot = computed(() => devices.value.filter(d => d.health_state === 'overheat').length)
let stop = () => {}
onMounted(() => { stop = poll(async signal => {
  try { devices.value = await api<Device[]>('/devices', {}, signal); error.value = '' }
  catch (e) { if (!signal.aborted) error.value = (e as Error).message }
  finally { loading.value = false }
}, 2000) })
onUnmounted(() => stop())
</script>
<template>
  <div class="page-heading"><div><p class="eyebrow">FLEET MONITOR / 01</p><h1>设备总览</h1><p class="muted">掌握设备连接、温度与数据新鲜度。</p></div><span class="refresh-note">↻ 每 2 秒更新</span></div>
  <div v-if="error" role="alert" class="alert">{{ error }}。下次轮询将自动重试；当前显示可能是旧数据。</div>
  <div class="summary-strip"><div><span>设备总数</span><strong>{{ devices.length || '—' }}<small> 台</small></strong></div><div><span>当前在线</span><strong>{{ online }}<small> 台</small></strong></div><div><span>过温告警</span><strong :class="{ orange: hot }">{{ hot }}<small> 台</small></strong></div><div class="summary-note"><span>演示阈值</span><strong>60<small> °C</small></strong><small>仅用于合成过温规则</small></div></div>
  <div class="section-title"><h2>设备列表</h2><span class="muted">固定设备 CHG-001 — CHG-003</span></div>
  <p v-if="loading" role="status">正在加载设备…</p>
  <p v-else-if="!devices.length && !error" class="empty">暂无设备数据</p>
  <div class="device-grid"><article v-for="(device, index) in devices" :key="device.device_id" class="device-card" data-testid="device-card" :data-message-id="device.message_id" :class="{ hot: device.health_state === 'overheat' }">
    <div class="card-top"><span class="device-number">0{{ index + 1 }}</span><span class="pill" :class="device.connection_state">{{ connectionLabels[device.connection_state] }}</span></div>
    <div class="charger-mark" aria-hidden="true"><span>ϟ</span><i></i></div>
    <h2>{{ device.device_id }}</h2><p class="device-label">模拟充电桩 / DC CHARGER</p>
    <div class="temperature">{{ device.temperature_c === null ? '—' : device.temperature_c.toFixed(1) }}<span> °C</span></div>
    <p class="health" :class="device.health_state">{{ healthLabels[device.health_state] }}<span v-if="!device.data_fresh"> · 数据过期 / 未知</span></p>
    <div class="mini-metrics"><div><small>功率</small><b>{{ metric(device.power_kw, 'kW') }}</b></div><div><small>电压</small><b>{{ metric(device.voltage_v, 'V') }}</b></div></div>
    <p class="sample-time">样本 {{ stamp(device.sample_ts) }}</p>
    <RouterLink class="card-link" :to="`/devices/${device.device_id}`" :aria-label="`查看 ${device.device_id}`">查看详情与历史 <span>↗</span></RouterLink>
  </article></div>
  <div class="info-band"><span>i</span><div><b>连接状态与数据新鲜度分别判定</b><p>在线不一定代表数据新鲜。超过 10 秒的指标显示为最后记录；最后新鲜接收超过 15 秒才判离线。</p></div><RouterLink to="/agent">向 Agent 提问 →</RouterLink></div>
</template>
