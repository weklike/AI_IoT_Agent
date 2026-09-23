<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, post } from '../api'
import { poll } from '../polling'
import { runLabels, terminal, type Run, type Submission } from '../types'
import ToolTrace from '../components/ToolTrace.vue'
import WorkOrders from '../components/WorkOrders.vue'
import MarkdownAnswer from '../components/MarkdownAnswer.vue'
import KnowledgeSources from '../components/KnowledgeSources.vue'
import PatrolReport from '../components/PatrolReport.vue'
import RunHistory from '../components/RunHistory.vue'
const route = useRoute(), router = useRouter()
const reportId = computed(() => typeof route.query.report === 'string' ? route.query.report : '')
const question = ref(''), allowed = ref(false), sending = ref(false), error = ref('')
const run = ref<Run>(), runId = ref(''), submitted = ref<Submission>()
let stop = () => {}, disposed = false
const storageKey = 'charge-ops-submission-v1'
const viewedKey = 'charge-ops-v2-viewed-run'
const submitAbort = new AbortController()
function selectRun(id: string) { if (reportId.value) void router.replace('/agent'); stop(); run.value = undefined; runId.value = id; submitted.value = undefined; localStorage.setItem(viewedKey, id); observe() }
function persist() { localStorage.setItem(storageKey, JSON.stringify({ body: submitted.value, run_id: runId.value })) }
function observe() {
  stop()
  stop = poll(async signal => {
    try {
      run.value = await api<Run>(`/agent/runs/${runId.value}`, {}, signal)
      error.value = ''
      if (terminal(run.value.status)) {
        return false
      }
    } catch (e) { if (!signal.aborted) error.value = (e as Error).message; return false }
  }, 1000)
}
async function send() {
  if (sending.value || runId.value) return
  if (!question.value.trim()) { error.value = '请输入问题'; return }
  if (!submitted.value) submitted.value = { request_id: crypto.randomUUID(), question: question.value, allow_work_order: allowed.value }
  localStorage.removeItem(viewedKey); persist(); sending.value = true; error.value = ''
  try {
    const response = await post<{ run_id: string }>('/agent/runs', submitted.value, submitAbort.signal)
    runId.value = response.run_id; persist()
    if (!disposed) observe()
  } catch (e) { error.value = (e as Error).message + '。可使用下方按钮复用原请求重试。' }
  finally { sending.value = false }
}
function reset() { stop(); run.value = undefined; runId.value = ''; submitted.value = undefined; error.value = ''; localStorage.removeItem(storageKey); localStorage.removeItem(viewedKey) }
onMounted(() => {
  if (reportId.value) return
  try {
    const viewed = localStorage.getItem(viewedKey)
    if (viewed) { runId.value = viewed; observe(); return }
    const raw = localStorage.getItem(storageKey)
    if (raw) {
      const saved = JSON.parse(raw) as { body?: Submission; run_id?: string }
      if (saved.body && typeof saved.body.request_id === 'string' && typeof saved.body.question === 'string') {
        submitted.value = saved.body; question.value = saved.body.question; allowed.value = saved.body.allow_work_order
        runId.value = saved.run_id || ''
        if (runId.value) observe()
        else error.value = '上次提交结果未确认，请复用原请求重试。'
      }
    }
  } catch { error.value = '无法恢复上次任务，请开始新任务。' }
})
onUnmounted(() => { disposed = true; submitAbort.abort(); stop() })
</script>
<template>
  <div class="page-heading"><div><p class="eyebrow">OPERATIONS ASSISTANT / 02</p><h1>Agent 助手</h1><p class="muted">从设备数据到排查依据，每一次工具调用都有记录。</p></div><span class="refresh-note">单任务执行</span></div>
  <RunHistory :selected-id="runId" :status="run?.status" :disabled="!!runId && (!run || !terminal(run.status))" @select="selectRun" />
  <PatrolReport v-if="reportId" :report-id="reportId" />
  <div class="agent-layout"><section class="panel compose-panel"><div class="assistant-icon">⌘</div><h2>今天需要检查什么？</h2><p class="muted">例如：分析 2 号桩最近 10 分钟的温度，给出排查建议。</p><label for="question">问题</label><textarea id="question" v-model="question" maxlength="2000" rows="6" :disabled="!!submitted" placeholder="输入设备与需要完成的任务…"></textarea><label class="permission"><input v-model="allowed" type="checkbox" :disabled="!!submitted">允许本次创建检修工单</label><p class="small-note">默认只读。建单需要明确请求、有效证据与本次授权。</p><button v-if="!runId" class="primary full" :disabled="sending" @click="send">{{ sending ? '正在提交…' : submitted ? '重试原请求' : '发送任务' }} <span>↗</span></button><button v-if="run && terminal(run.status)" class="primary full" @click="reset">开始新任务</button><button v-if="error && runId" @click="observe">重新获取任务状态</button><p v-if="error" role="alert" class="alert">{{ error }}</p><div class="capabilities"><b>可用业务能力</b><span>设备状态 · 历史统计</span><span>知识检索 · 站点汇总 · 巡检报告</span><span>会话 · 工单 · 事件时间线</span><span>唯一写入能力：授权建单</span></div></section>
    <div class="agent-results"><section v-if="!runId" class="panel awaiting"><div>↗</div><h2>等待一个运维任务</h2><p>提交后在这里查看结果与实际工具轨迹。</p><p class="muted">设备采用合成数据。fixture 模式只验证工程流程。</p></section><section v-else class="panel answer-panel"><div class="section-title"><h2>执行结果</h2><span data-testid="run-status" class="pill" :class="{ online: run?.status === 'completed', offline: run && ['failed', 'timed_out', 'interrupted'].includes(run.status) }">{{ run ? runLabels[run.status] : '正在获取' }}</span></div><small class="run-id" data-testid="run-id">{{ runId }}</small><p v-if="run?.error_code" class="alert">{{ run.error_code }} · 本次任务未正常完成，请检查原因后发起新任务。</p><MarkdownAnswer v-if="run?.answer" :content="run.answer" /><p v-else class="answer">正在查询设备与工具结果…</p></section><KnowledgeSources v-if="run?.answer_refs" :references="run.answer_refs" /><ToolTrace v-if="runId" :calls="run?.tool_calls || []" :references="run?.answer_refs || []" /><WorkOrders v-if="run && terminal(run.status)" /></div>
  </div>
</template>
