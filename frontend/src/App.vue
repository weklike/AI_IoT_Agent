<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from './api'
const route = useRoute()
const mode = ref('正在连接')
onMounted(async () => {
  try { const health = await api<{ llm_mode: string }>('/health'); mode.value = health.llm_mode === 'fixture' ? 'fixture · 替身模型' : 'real · 真实模型' }
  catch { mode.value = '服务未就绪' }
})
</script>
<template>
  <div class="shell">
    <aside class="sidebar">
      <a class="brand" href="/devices"><span class="brand-icon">ϟ</span><div>CHARGE OPS<small>设备监控与运维</small></div></a>
      <div class="edition-label">V2.0 <span>CHARGING OPERATIONS</span></div>
      <p class="nav-caption">工作空间 / WORKSPACE</p>
      <nav><RouterLink to="/devices" :class="{ selected: route.path.startsWith('/devices') }"><span>◫</span> 设备总览 <small>01</small></RouterLink><RouterLink to="/agent"><span>⌘</span> Agent 助手 <small>02</small></RouterLink></nav>
      <div class="sidebar-bottom"><span class="status-dot"></span> 软件模拟环境<p>3 台充电设备 · 单机演示</p><small>所有数值来自合成遥测。<br>过温阈值为演示规则。</small></div>
    </aside>
    <div class="workspace"><header class="topbar"><span>充电运维工作站 <span class="muted">/ 从设备数据到处理记录</span></span><span class="mode-badge">{{ mode }}</span></header>
      <main><RouterView :key="route.path" /></main><footer>CHARGE OPERATIONS <span>MQTT 设备链路 · 数据时间以样本为准</span></footer>
    </div>
  </div>
</template>
