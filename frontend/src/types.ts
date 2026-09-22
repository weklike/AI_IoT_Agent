export interface Device {
  message_id: string | null; device_id: string; name: string; connection_state: 'unknown' | 'online' | 'offline'
  health_state: 'unknown' | 'normal' | 'overheat'; data_fresh: boolean
  data_age_seconds: number | null; sample_ts: string | null
  temperature_c: number | null; voltage_v: number | null; current_a: number | null; power_kw: number | null
}
export interface Sample { gap_before: boolean; message_id: string; sample_ts: string; temperature_c: number; voltage_v: number; current_a: number; power_kw: number }
export interface Command { command_id: string; status: 'pending' | 'applied' | 'rejected' | 'timed_out'; scenario?: string }
export interface ToolCall { tool_call_id: string; provider_call_id: string; tool_name: string; args_json: Record<string, unknown>; result_json: unknown; status: string; duration_ms: number | null; error_code: string | null }
export interface Run { run_id: string; request_id: string; question: string; status: string; answer: string | null; error_code: string | null; tool_calls: ToolCall[]; llm_mode: string }
export interface WorkOrder { order_id: string; device_id: string; reason_code: string; status: string; created_at: string }
export interface Submission { request_id: string; question: string; allow_work_order: boolean }
export const connectionLabels = { unknown: '状态未知', online: '在线', offline: '离线' }
export const healthLabels = { unknown: '健康状态未知', normal: '正常', overheat: '过温告警' }
export const runLabels: Record<string, string> = { queued: '等待执行', running: '执行中', completed: '已完成', failed: '执行失败', timed_out: '执行超时', interrupted: '任务已中断' }
export const terminal = (status: string) => ['completed', 'failed', 'timed_out', 'interrupted'].includes(status)
export const stamp = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '暂无样本'
export const metric = (value: number | null, unit: string) => value === null ? '—' : `${value.toFixed(1)} ${unit}`
