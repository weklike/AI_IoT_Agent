import { onUnmounted, ref } from 'vue'
import { api, ApiError } from './api'

interface Pending { path: string; method: string; body: Record<string, unknown> & { request_id: string } }
// Keep uncertain writes across refresh; a retry sends exactly the original request and parameters.
export function useMutation(key: string) {
  const storageKey = `charge-ops-v2-operation:${key}`
  const busy = ref(false), error = ref(''), pending = ref<Pending>()
  const controller = new AbortController()
  try {
    const saved: Pending | null = JSON.parse(localStorage.getItem(storageKey) || 'null')
    if (saved && typeof saved.path === 'string' && typeof saved.body?.request_id === 'string') pending.value = saved
  } catch { error.value = '无法恢复上次请求，请检查浏览器存储。' }
  onUnmounted(() => controller.abort())
  async function execute<T>(path: string, body: Record<string, unknown> = {}, method = 'POST'): Promise<T | undefined> {
    if (busy.value || controller.signal.aborted) return
    if (pending.value && (pending.value.path !== path || pending.value.method !== method)) {
      error.value = '上次操作结果未确认，请先重试原请求。'; return
    }
    busy.value = true; error.value = ''
    try {
      pending.value ??= { path, method, body: { ...body, request_id: crypto.randomUUID() } }
      localStorage.setItem(storageKey, JSON.stringify(pending.value))
      const result = await api<T>(pending.value.path, { method: pending.value.method, body: JSON.stringify(pending.value.body) }, controller.signal)
      if (controller.signal.aborted) return
      pending.value = undefined; localStorage.removeItem(storageKey)
      return result
    } catch (failure) {
      if (!controller.signal.aborted) error.value = failure instanceof Error ? failure.message : '操作失败'
      if (failure instanceof ApiError && failure.status !== undefined && failure.status >= 400 && failure.status < 500) {
        pending.value = undefined; localStorage.removeItem(storageKey)
      }
    } finally { busy.value = false }
  }
  function retry<T>() { return pending.value ? execute<T>(pending.value.path, pending.value.body, pending.value.method) : Promise.resolve(undefined) }
  return { busy, error, pending, execute, retry }
}
