export class ApiError extends Error {
  constructor(public code: string, message: string) { super(message) }
}
export async function api<T>(path: string, options: RequestInit = {}, signal?: AbortSignal): Promise<T> {
  try {
    const response = await fetch(`/api${path}`, { ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
      signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(7000)]) : AbortSignal.timeout(7000) })
    const body = await response.json()
    if (!response.ok) throw new ApiError(body.error?.code || 'SERVICE_UNAVAILABLE', body.error?.message || '服务未就绪，请稍后重试')
    return body.data as T
  } catch (error) {
    if (signal?.aborted) throw error
    if (error instanceof ApiError) throw error
    throw new ApiError('NETWORK_ERROR', '服务连接失败，请检查后端连接后重试')
  }
}
export const post = <T>(path: string, body: unknown, signal?: AbortSignal) => api<T>(path, { method: 'POST', body: JSON.stringify(body) }, signal)
