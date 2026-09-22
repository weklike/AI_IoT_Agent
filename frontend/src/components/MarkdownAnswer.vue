<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '../markdown'

const props = defineProps<{ content: string }>()
const html = computed(() => renderMarkdown(props.content))
</script>

<template>
  <article class="answer markdown-answer" v-html="html"></article>
</template>

<style scoped>
.markdown-answer {
  white-space: normal;
  overflow-wrap: anywhere;
  font-size: 14px;
  line-height: 1.85;
}
.markdown-answer :deep(> :first-child) { margin-top: 0; }
.markdown-answer :deep(> :last-child) { margin-bottom: 0; }
.markdown-answer :deep(p) { margin: 0 0 1em; line-height: inherit; }
.markdown-answer :deep(h3), .markdown-answer :deep(h4),
.markdown-answer :deep(h5), .markdown-answer :deep(h6) {
  margin: 1.6em 0 .65em;
  line-height: 1.5;
  font-weight: 600;
  color: #203b3d;
}
.markdown-answer :deep(h3) { font-size: 19px; padding-bottom: .5em; border-bottom: 1px solid var(--line); }
.markdown-answer :deep(h4) { font-size: 16px; }
.markdown-answer :deep(h5), .markdown-answer :deep(h6) { font-size: 14px; }
.markdown-answer :deep(strong) { font-weight: 650; color: #203b3d; }
.markdown-answer :deep(ul), .markdown-answer :deep(ol) { margin: .7em 0 1.15em; padding-left: 1.7em; }
.markdown-answer :deep(li) { padding-left: .15em; margin: .3em 0; }
.markdown-answer :deep(li > ul), .markdown-answer :deep(li > ol) { margin: .3em 0; }
.markdown-answer :deep(li > p) { margin: .3em 0; }
.markdown-answer :deep(li::marker) { color: #657f61; font-weight: 600; }
.markdown-answer :deep(blockquote) {
  margin: 1.25em 0;
  padding: 12px 16px;
  border-left: 3px solid #9eaf83;
  background: #f5f7ef;
  color: #53665c;
  border-radius: 0 5px 5px 0;
}
.markdown-answer :deep(blockquote > :last-child) { margin-bottom: 0; }
.markdown-answer :deep(a) { color: #37685d; text-decoration: underline; text-underline-offset: 3px; }
.markdown-answer :deep(code) {
  font-family: Consolas, 'Liberation Mono', monospace;
  font-size: .9em;
  background: #f0f3ec;
  padding: 2px 5px;
  border-radius: 3px;
}
.markdown-answer :deep(pre) {
  max-width: 100%;
  max-height: none;
  margin: 1.2em 0;
  padding: 16px;
  white-space: pre;
  overflow-wrap: normal;
  overflow: auto;
  background: #f5f7f2;
  border: 1px solid var(--line);
  border-radius: 5px;
  font-size: 12px;
  line-height: 1.7;
}
.markdown-answer :deep(pre code) { padding: 0; background: transparent; font-size: inherit; }
.markdown-answer :deep(.markdown-table) { max-width: 100%; overflow-x: auto; margin: 1.2em 0; border: 1px solid var(--line); border-radius: 5px; }
.markdown-answer :deep(.markdown-table:focus-visible) { outline: 2px solid #ce5b35; outline-offset: 3px; }
.markdown-answer :deep(table) { width: 100%; border-collapse: collapse; font-size: 13px; }
.markdown-answer :deep(th), .markdown-answer :deep(td) { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--line); min-width: 100px; }
.markdown-answer :deep(th) { color: #405a4e; font-weight: 600; background: #f1f5e9; }
.markdown-answer :deep(tbody tr:nth-child(even)) { background: #fafbf8; }
.markdown-answer :deep(tbody tr:last-child td) { border-bottom: 0; }
.markdown-answer :deep(hr) { border: 0; border-top: 1px solid var(--line); margin: 1.5em 0; }
</style>
