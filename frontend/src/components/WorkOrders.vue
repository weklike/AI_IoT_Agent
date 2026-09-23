<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { poll } from '../polling'
import type { Page, WorkOrder } from '../types'
import WorkOrderItem from './WorkOrderItem.vue'
const props = defineProps<{ deviceId?: string }>()
const rows = ref<WorkOrder[]>([]), cursor = ref<string | null>(null), state = ref(''), error = ref(''), loading = ref(true), browsing = ref(false)
const lifetime = new AbortController()
let stop = () => {}
async function load(signal: AbortSignal = lifetime.signal, more = false) {
  loading.value = true
  try { const query = new URLSearchParams({ limit: '20' }); if (props.deviceId) query.set('device_id', props.deviceId); if (state.value) query.set('state', state.value); if (more && cursor.value) query.set('cursor', cursor.value); const page = await api<Page<WorkOrder>>(`/work-orders?${query}`, {}, signal); rows.value = more ? [...rows.value, ...page.items] : page.items; cursor.value = page.next_cursor; error.value = '' }
  catch (e) { if (!signal.aborted) error.value = (e as Error).message }
  finally { if (!signal.aborted) loading.value = false }
}
function merge(order: WorkOrder, value: Partial<WorkOrder>) { if (value.version === undefined || value.version >= order.version) Object.assign(order, value) }
function resume() { stop(); browsing.value = false; stop = poll(signal => load(signal), 2000) }
async function more() { stop(); browsing.value = true; await load(lifetime.signal, true) }
onMounted(resume); onUnmounted(() => { stop(); lifetime.abort() })
</script>
<template>
  <section class="panel" data-testid="work-orders"><div class="section-title"><h2>检修工单 <small>当前显示 {{ rows.length }}</small></h2><label>工单状态<select v-model="state" @change="resume"><option value="">全部状态</option><option value="UNCLOSED">所有未关闭</option><option>OPEN</option><option>IN_PROGRESS</option><option>RESOLVED</option><option>CLOSED</option></select></label></div><p v-if="loading && !rows.length">正在加载工单…</p><p v-else-if="!rows.length && !error" class="muted">暂无工单。仅在本次授权且有有效证据时创建。</p><p v-if="error" role="alert" class="alert">{{ error }}</p><WorkOrderItem v-for="order in rows" :key="order.order_id" :order="order" @changed="merge(order, $event)" /><div class="form-row"><button v-if="cursor" :disabled="loading" @click="more">加载更早工单</button><button v-if="browsing" @click="resume">返回最新工单</button></div></section>
</template>
