export interface Device {
  message_id: string | null; device_id: string; name: string; connection_state: 'unknown' | 'online' | 'offline'
  health_state: 'unknown' | 'normal' | 'overheat'; data_fresh: boolean
  data_age_seconds: number | null; sample_ts: string | null
  schema_version: number | null; session_id: string | null; session_state: string | null; requested_power_w: number | null; power_limit_w: number | null; meter_total_wh: number | null; session_energy_wh: number | null; applied_control_generation: number | null
  temperature_c: number | null; voltage_v: number | null; current_a: number | null; power_kw: number | null
}
export interface Sample { gap_before: boolean; message_id: string; sample_ts: string; temperature_c: number; voltage_v: number; current_a: number; power_kw: number }
export interface Command { command_id: string; status: 'pending' | 'applied' | 'rejected' | 'timed_out'; scenario?: string }
export interface ToolCall { tool_call_id: string; provider_call_id: string; tool_name: string; args_json: Record<string, unknown>; result_json: unknown; status: string; duration_ms: number | null; error_code: string | null }
export interface Run { answer_refs: AnswerRef[] | null; kind: string; run_id: string; request_id: string; question: string; status: string; answer: string | null; error_code: string | null; tool_calls: ToolCall[]; llm_mode: string }
export interface WorkOrder { version: number; closed_at: string | null; alarm_id: string | null; order_id: string; device_id: string; reason_code: string; status: string; created_at: string }
export interface Submission { request_id: string; question: string; allow_work_order: boolean }
export const connectionLabels = { unknown: '状态未知', online: '在线', offline: '离线' }
export const healthLabels = { unknown: '健康状态未知', normal: '正常', overheat: '过温告警' }
export const runLabels: Record<string, string> = { queued: '等待执行', running: '执行中', completed: '已完成', failed: '执行失败', timed_out: '执行超时', interrupted: '任务已中断' }
export const terminal = (status: string) => ['completed', 'failed', 'timed_out', 'interrupted'].includes(status)
export const stamp = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '暂无样本'
export const metric = (value: number | null, unit: string) => value === null ? '—' : `${value.toFixed(1)} ${unit}`

export interface Page<T> { items: T[]; next_cursor: string | null }
export interface DeviceCommand { action: string; command_id: string; status: string; verification_status: string; error_code: string | null; args_json: { session_id?: string }; generation: number }
export interface ChargingSession { session_id: string; device_id: string; status: string; requested_power_w: number; started_at: string | null; ended_at: string | null; observed_at: string | null; energy_wh: number | null; meter_quality: string | null; report_missing: boolean; duration_seconds: number | null }
export interface ChargingStatistics { session_count: number; active_count: number; missing_report_count: number; completed_session_energy_wh: number | null; ended_session_count: number; from: string; to: string }
export interface StationState { budget_w: number; revision: number; executing_plan_id: string | null }
export interface PowerPlan { plan_id: string; status: string; budget_w: number; created_at: string; allocation_json: Record<string, number>; results_json: Record<string, unknown>; confirmed_budget_w: number; protection_budget_w: number; commands: Record<string, Pick<DeviceCommand, 'command_id' | 'status' | 'verification_status' | 'error_code'>> }
export interface Alarm { alarm_id: string; device_id: string; reason_code: string; condition: string; version: number; acknowledged_at: string | null; evaluation_state: string; started_at: string; cleared_at: string | null; peak_temperature_c: number | null }
export interface AlarmRule { device_id: string; reason_code: string; enabled: boolean; version: number; trigger_duration_seconds: number; clear_below_c: number; clear_duration_seconds: number }
export interface FleetDevice { device_id: string; status: Device; statistics: { from: string; to: string; sample_count: number; temperature_avg_c: number | null; temperature_max_c: number | null; power_avg_kw: number | null }; active_alarms: Alarm[]; charging_statistics: ChargingStatistics }
export interface FleetOverview { from: string; to: string; window_minutes: number; devices: FleetDevice[]; station: StationState; latest_plan: { plan_id: string; status: string; budget_w: number; confirmations: PowerPlan['commands'] } | null }
export type AnswerRef = { kind: 'DATA'; tool_call_id: string } | { kind: 'KB'; tool_call_id: string; source_id: string; version: string; chunk_id: string; hash: string }
export interface Patrol { report_id: string; run_id: string | null; trigger: string; status: string; created_at: string; window_minutes: number; snapshot_json: FleetOverview | null; refs_json: AnswerRef[] | null }
export interface PatrolSchedule { enabled: boolean; version: number; interval_seconds: number; window_minutes: number; next_due_at: string | null }
export interface KnowledgeSource { source_id: string; version: string; title: string; source_kind: string; source_url: string | null; license_note: string; content: string; chunks: { chunk_id: string; content: string }[] }
export interface TimelineEvent { device_id: string; source_type: string; source_id: string; observed_at: string; received_at: string | null; late_received: boolean | null; detail: Record<string, unknown> }
export interface Timeline extends Page<TimelineEvent> { event_count: number; counts_by_source: Record<string, number>; truncated: boolean; from: string; to: string }
export interface ScenarioScript { script_id: string; script_name: string; status: string; cancel_reason: string | null; steps_json: { scenario: string; offset_seconds: number; command_id: string; status: string }[]; commands: Command[] }
export interface RunSummary { run_id: string; question: string; status: string; kind: string; created_at: string }
export interface WorkOrderEvent { event_id: string; from_status: string; to_status: string; note: string; checked_at: string; evidence_json: Record<string, unknown> }
export const commandLabels: Record<string, string> = { pending: '等待回执', applied: '收到设备回执', rejected: '设备拒绝', timed_out: '回执超时，结果未确认', interrupted: '命令已中断' }
export const verificationLabels: Record<string, string> = { pending: '等待效果验证', verified: '效果已验证', unconfirmed: '效果未确认' }
export const planLabels: Record<string, string> = { PREVIEW: '仅预览，尚未下发', EXECUTING: '执行中，逐设备确认', VERIFIED: '全部效果已验证', PARTIAL: '部分完成，存在未确认结果', INTERRUPTED: '执行中断' }
export const eventLabels: Record<string, string> = { device_command: '充电控制命令', device_ack: '设备回执', device_late_ack: '晚到设备回执', scenario_command: '场景命令', scenario_ack: '场景回执', scenario_late_ack: '晚到场景回执', session_report: '会话报告', alarm_event: '告警事件', work_order_created: '创建工单', work_order_event: '工单处理', tool_call: '工具调用' }
