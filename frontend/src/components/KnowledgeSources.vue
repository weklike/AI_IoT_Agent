<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { api } from '../api'
import type { AnswerRef, KnowledgeSource } from '../types'
const props = defineProps<{ references: AnswerRef[] }>()
const refs = computed(() => props.references.filter((item): item is Extract<AnswerRef, { kind: 'KB' }> => item.kind === 'KB'))
const loaded = ref<Record<string, KnowledgeSource>>({}), error = ref(''), busy = ref('')
const controller = new AbortController()
async function open(source: Extract<AnswerRef, { kind: 'KB' }>) {
  const key = `${source.source_id}@${source.version}`; if (busy.value) return
  busy.value = key; error.value = ''
  try { loaded.value[key] = await api<KnowledgeSource>(`/knowledge/sources/${encodeURIComponent(source.source_id)}/versions/${encodeURIComponent(source.version)}`, {}, controller.signal) }
  catch (e) { if (!controller.signal.aborted) error.value = (e as Error).message }
  finally { busy.value = '' }
}
onUnmounted(() => controller.abort())
</script>
<template>
  <section v-if="refs.length" class="panel" data-testid="knowledge-sources"><p class="eyebrow">KNOWLEDGE / 可追溯依据</p><h2>知识来源</h2><p class="muted">以下引用已经由服务器校验为本轮成功检索结果。资料只解释模拟系统，排名不是诊断概率。</p><p v-if="error" role="alert" class="alert">{{ error }}</p>
    <article v-for="source in refs" :key="`${source.source_id}@${source.version}#${source.chunk_id}`" class="source-card"><div class="section-title"><b>{{ source.source_id }} · v{{ source.version }}</b><button :disabled="!!busy" @click="open(source)">查看来源原文</button></div><small class="run-id">块 {{ source.chunk_id }} · 依据工具 {{ source.tool_call_id }}</small><div v-if="loaded[`${source.source_id}@${source.version}`]" data-testid="source-content"><h3>{{ loaded[`${source.source_id}@${source.version}`].title }}</h3><p class="muted">{{ loaded[`${source.source_id}@${source.version}`].source_kind }} · {{ loaded[`${source.source_id}@${source.version}`].license_note }}</p><pre class="source-text">{{ loaded[`${source.source_id}@${source.version}`].chunks.find(chunk => chunk.chunk_id === source.chunk_id)?.content }}</pre><details><summary>完整原文与元数据</summary><pre>{{ loaded[`${source.source_id}@${source.version}`].content }}</pre></details></div></article>
  </section>
</template>
