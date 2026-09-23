<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api'
import { runLabels, stamp, type Page, type RunSummary } from '../types'
const props = defineProps<{ selectedId: string; status?: string; disabled?: boolean }>()
const emit = defineEmits<{ select: [id: string] }>()
const rows = ref<RunSummary[]>([]), cursor = ref<string | null>(null), loading = ref(false), error = ref('')
const lifetime = new AbortController()
async function load(more = false) {
  if (loading.value) return
  loading.value = true
  try { const page = await api<Page<RunSummary>>(`/agent/runs?limit=20${more && cursor.value ? `&cursor=${cursor.value}` : ''}`, {}, lifetime.signal); rows.value = more ? [...rows.value, ...page.items] : page.items; cursor.value = page.next_cursor; error.value = '' }
  catch (e) { if (!lifetime.signal.aborted) error.value = (e as Error).message }
  finally { loading.value = false }
}
function choose(event: Event) { const id = (event.target as HTMLSelectElement).value; if (id) emit('select', id) }
onMounted(() => load()); watch(() => props.selectedId, () => load()); onUnmounted(() => lifetime.abort())
</script>
<template>
  <section class="panel history-picker"><div class="form-row"><label>历史任务<select :value="selectedId" :disabled="disabled || loading" @change="choose"><option value="">选择已保存任务</option><option v-if="selectedId && !rows.some(row => row.run_id === selectedId)" :value="selectedId">当前任务 {{ selectedId }}</option><option v-for="row in rows" :key="row.run_id" :value="row.run_id">{{ stamp(row.created_at) }} · {{ row.kind === 'patrol' ? '巡检' : '聊天' }} · {{ runLabels[row.run_id === selectedId && status ? status : row.status] || row.status }} · {{ row.question.slice(0, 35) }}</option></select></label><button :disabled="loading" @click="load()">刷新历史</button><button v-if="cursor" :disabled="loading" @click="load(true)">加载更早任务</button></div><p class="muted">历史工具轨迹只用于复盘，不自动成为新任务的当前依据。</p><p v-if="error" role="alert" class="alert">{{ error }}</p></section>
</template>
