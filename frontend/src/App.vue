<script setup lang="ts">
import { onMounted, ref } from 'vue'
const state = ref('正在检查后端连接…')
onMounted(async () => {
  try {
    const response = await fetch('/api/health', { signal: AbortSignal.timeout(5000) })
    const result = await response.json()
    state.value = `DB: ${result.data.db} · MQTT: ${result.data.mqtt} · 模型模式: ${result.data.llm_mode}`
  } catch { state.value = '服务连接失败，请检查后端。' }
})
</script>
<template><main><p>CHARGE OPS / 开发骨架</p><h1>充电设备监控与运维</h1><p>{{ state }}</p><p>Task 1 占位首页：业务页面尚未实现。</p></main></template>
<style>body{font-family:system-ui,sans-serif;background:#f4f5f7;color:#172b36;margin:0}main{max-width:900px;margin:10vh auto;padding:32px}h1{font-size:36px}</style>
