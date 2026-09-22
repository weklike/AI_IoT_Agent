<script setup lang="ts">
import { stamp, type WorkOrder } from '../types'
defineProps<{ orders: WorkOrder[] }>()
</script>
<template><section class="panel" data-testid="work-orders"><h2>检修工单 <small>{{ orders.length }}</small></h2><p v-if="!orders.length" class="muted">暂无工单。仅在本次授权且有有效证据时创建。</p><div v-for="order in orders" :key="order.order_id" class="order-row"><b>{{ order.device_id }} · {{ order.reason_code }}</b><span class="pill">{{ order.status }}</span><code>{{ order.order_id }}</code><small>{{ stamp(order.created_at) }}</small></div></section></template>
