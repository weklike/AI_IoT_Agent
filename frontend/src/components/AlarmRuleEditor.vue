<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { useMutation } from '../mutations'
import type { AlarmRule } from '../types'
const props = defineProps<{ deviceId: string; reason: 'OVERHEAT' | 'OFFLINE' }>()
const rule = ref<AlarmRule>(), error = ref(''), saved = ref(false), loading = ref(false)
const operation = useMutation(`rule:${props.deviceId}:${props.reason}`), lifetime = new AbortController()
const invalid = computed(() => rule.value && props.reason === 'OVERHEAT' && (!Number.isInteger(rule.value.trigger_duration_seconds) || rule.value.trigger_duration_seconds < 0 || rule.value.trigger_duration_seconds > 60 || !Number.isInteger(rule.value.clear_duration_seconds) || rule.value.clear_duration_seconds < 0 || rule.value.clear_duration_seconds > 60 || !Number.isFinite(rule.value.clear_below_c) || rule.value.clear_below_c < -20 || rule.value.clear_below_c >= 60))
async function load() { if (loading.value) return; loading.value = true; try { rule.value = await api<AlarmRule>(`/alarm-rules/${props.deviceId}/${props.reason}`, {}, lifetime.signal); error.value = ''; saved.value = false } catch (e) { if (!lifetime.signal.aborted) error.value = (e as Error).message } finally { loading.value = false } }
async function save() {
  if (!rule.value) return
  const fields = props.reason === 'OVERHEAT' ? { trigger_duration_seconds: rule.value.trigger_duration_seconds, clear_below_c: rule.value.clear_below_c, clear_duration_seconds: rule.value.clear_duration_seconds } : {}
  const result = await operation.execute<AlarmRule>(`/alarm-rules/${props.deviceId}/${props.reason}`, { expected_version: rule.value.version, enabled: rule.value.enabled, ...fields }, 'PUT')
  if (result) { rule.value = result; saved.value = true }
}
onMounted(load); onUnmounted(() => lifetime.abort())
</script>
<template>
  <div class="rule-editor" :data-testid="`alarm-rule-${reason}`"><h3>{{ reason === 'OVERHEAT' ? '过温规则' : '离线规则' }}</h3><div v-if="rule" class="form-row"><label class="inline-checkbox"><input v-model="rule.enabled" type="checkbox" :disabled="operation.busy.value || !!operation.pending.value">启用{{ reason === 'OVERHEAT' ? '过温' : '离线' }}告警</label><template v-if="reason === 'OVERHEAT'"><label>触发持续（秒）<input v-model.number="rule.trigger_duration_seconds" type="number" min="0" max="60" step="1" :disabled="operation.busy.value || !!operation.pending.value"></label><label>恢复温度低于（°C）<input v-model.number="rule.clear_below_c" type="number" min="-20" max="59.9" step="0.1" :disabled="operation.busy.value || !!operation.pending.value"></label><label>恢复持续（秒）<input v-model.number="rule.clear_duration_seconds" type="number" min="0" max="60" step="1" :disabled="operation.busy.value || !!operation.pending.value"></label></template><button :disabled="operation.busy.value || !!invalid" @click="save">{{ operation.pending.value ? '重试原规则请求' : '保存规则' }}</button><small>版本 {{ rule.version }}</small></div><p v-if="saved" class="notice">规则已保存；已有活动告警继续使用触发时的规则快照。</p><p v-if="reason === 'OFFLINE'" class="muted">离线规则仅允许启用/禁用；15 秒离线阈值不可在此修改。</p><p v-if="error || operation.error.value" role="alert" class="alert">{{ error || operation.error.value }} <button :disabled="loading || !!operation.pending.value" @click="load">刷新当前版本</button></p></div>
</template>
