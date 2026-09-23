<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { useMutation } from '../mutations'
import { poll } from '../polling'
import { commandLabels, type ScenarioScript } from '../types'
const props = defineProps<{ deviceId: string }>()
const startRequest = useMutation(`script-start:${props.deviceId}`), cancelRequest = useMutation(`script-cancel:${props.deviceId}`)
const storageKey = `charge-ops-v2-script:${props.deviceId}`
const identifier = ref(localStorage.getItem(storageKey) || ''), script = ref<ScenarioScript>(), error = ref(''), name = ref('normal_overheat_normal')
const running = computed(() => !!identifier.value && (!script.value || script.value.status === 'running'))
const labels: Record<string, string> = { running: '运行中', completed: '已完成', cancelled: '已取消', interrupted: '已中断', failed: '执行失败' }
let stop = () => {}
function observe() {
  stop()
  stop = poll(async signal => {
    try { script.value = await api<ScenarioScript>(`/simulator/scripts/${identifier.value}`, {}, signal); error.value = ''; if (script.value.status !== 'running') return false }
    catch (e) { if (!signal.aborted) error.value = (e as Error).message; return false }
  }, 1000)
}
function accepted(id: string) { identifier.value = id; script.value = undefined; localStorage.setItem(storageKey, id); observe() }
async function start() { const result = await startRequest.execute<{ script_id: string }>('/simulator/scripts', { device_id: props.deviceId, script_name: name.value }); if (result) accepted(result.script_id) }
async function retryStart() { const result = await startRequest.retry<{ script_id: string }>(); if (result) accepted(result.script_id) }
async function cancel() { const result = await cancelRequest.execute(`/simulator/scripts/${identifier.value}/cancel`); if (result) observe() }
function clearView() { stop(); identifier.value = ''; script.value = undefined; error.value = ''; localStorage.removeItem(storageKey) }
onMounted(() => { if (identifier.value) observe() }); onUnmounted(() => stop())
</script>
<template>
  <section class="panel"><div class="section-title"><div><p class="eyebrow">SCENARIO SCRIPT / 可重复演示</p><h2>固定场景脚本</h2></div><span class="pill">20 / 20 / 20 秒</span></div><p class="muted">只切换模拟场景，不启停充电。页面离开后脚本继续；需要停止时显式取消剩余步骤。手动场景操作会取消该设备剩余脚本。</p><div class="form-row"><label>脚本场景<select v-model="name" :disabled="running || startRequest.busy.value || !!startRequest.pending.value"><option value="normal_overheat_normal">正常 → 过温 → 正常</option><option value="normal_offline_normal">正常 → 暂停上报 → 正常</option></select></label><button :disabled="running || startRequest.busy.value || !!startRequest.pending.value || !!cancelRequest.pending.value" @click="start">运行60秒脚本</button><button v-if="running || cancelRequest.pending.value" :disabled="cancelRequest.busy.value" @click="cancel">{{ cancelRequest.pending.value ? '重试原取消请求' : '取消剩余步骤' }}</button><button v-if="startRequest.pending.value" :disabled="startRequest.busy.value" @click="retryStart">重试原脚本请求</button></div>
    <div v-if="identifier" class="operation-result" data-testid="script-status"><strong>{{ script ? labels[script.status] || script.status : '正在查询' }}</strong><p class="run-id">{{ identifier }}</p><p v-if="script?.cancel_reason" class="muted">{{ script.cancel_reason }} · 取消不会额外切换当前场景。</p><ol v-if="script"><li v-for="step in script.steps_json" :key="step.command_id">第 {{ step.offset_seconds }} 秒 · {{ step.scenario }} · {{ commandLabels[script.commands.find(command => command.command_id === step.command_id)?.status || step.status] || step.status }}<small class="run-id"> {{ step.command_id }}</small></li></ol></div>
    <p v-if="error || startRequest.error.value || cancelRequest.error.value" role="alert" class="alert">{{ error || startRequest.error.value || cancelRequest.error.value }}</p><div v-if="error" class="form-row"><button @click="observe">重新查询脚本</button><button @click="clearView">清除本页脚本选择</button></div>
  </section>
</template>
