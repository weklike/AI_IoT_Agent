<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])
import type { Sample } from '../types'
const props = defineProps<{ samples: Sample[] }>()
const element = ref<HTMLDivElement>()
const gapCount = computed(() => props.samples.filter(sample => sample.gap_before).length)
let chart: echarts.ECharts | undefined, observer: ResizeObserver | undefined
const render = () => chart?.setOption({ animation: false, grid: { left: 48, right: 22, top: 26, bottom: 36 },
  tooltip: { trigger: 'axis', renderMode: 'richText' }, xAxis: { type: 'time', axisLabel: { color: '#75818b' } },
  yAxis: { type: 'value', name: '温度 / °C', axisLabel: { color: '#75818b' }, splitLine: { lineStyle: { color: '#e9edee' } } },
  series: [{ name: '温度 °C', type: 'line', showSymbol: true, symbolSize: 3, connectNulls: false, lineStyle: { color: '#eb6a3c', width: 2 },
    areaStyle: { color: '#eb6a3c', opacity: .07 }, data: props.samples.flatMap(p => p.gap_before ? [[p.sample_ts, null], [p.sample_ts, p.temperature_c]] : [[p.sample_ts, p.temperature_c]]) }] })
onMounted(() => { if (element.value) { chart = echarts.init(element.value); observer = new ResizeObserver(() => chart?.resize()); observer.observe(element.value); render() } })
watch(() => props.samples, render)
onUnmounted(() => { observer?.disconnect(); chart?.dispose() })
</script>
<template><p v-if="gapCount" class="small-note">含 {{ gapCount }} 段采集空窗，曲线不连接无样本区间。</p><div ref="element" class="chart" data-testid="telemetry-chart" :data-gap-count="gapCount" role="img" aria-label="历史温度曲线，横轴样本时间，纵轴摄氏度"></div></template>
