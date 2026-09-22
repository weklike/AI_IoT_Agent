<script setup lang="ts">
import type { ToolCall } from '../types'
defineProps<{ calls: ToolCall[] }>()
</script>
<template><section class="panel trace" data-testid="tool-trace"><h2>工具调用轨迹 <small>{{ calls.length }} 次</small></h2><p v-if="!calls.length" class="muted">等待服务器工具记录</p><details v-for="(call, index) in calls" :key="call.tool_call_id"><summary><span class="trace-index">{{ index + 1 }}</span><code>{{ call.tool_name }}</code><span class="pill" :class="{ offline: call.status === 'failed', online: call.status === 'succeeded' }">{{ { running: '执行中', succeeded: '成功', failed: '失败' }[call.status] || call.status }}</span></summary><p v-if="call.error_code" class="orange">{{ call.error_code }}</p><small>内部调用 {{ call.tool_call_id }} · {{ call.duration_ms?.toFixed(0) ?? '—' }} ms</small><pre>{{ JSON.stringify({ arguments: call.args_json, result: call.result_json }, null, 2) }}</pre></details></section></template>
