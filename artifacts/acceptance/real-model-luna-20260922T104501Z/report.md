# gpt-5.6-luna 真实模型重测

共完成 60 次案例执行，自动检查通过 36/60；总体状态 FAIL。人工语义与关键错误复核尚未执行，不能把自动通过数称为最终成功数。

模型及参数、prompt/Schema 摘要见 manifest.json；原始案例未修改。每例隔离临时库，未向演示库写入测试工单。

| 类别 | 自动通过 / 执行数 | 门槛 |
|---|---|---|
| 状态查询 | 12/12 | ≥9/12 |
| 历史统计 | 9/12 | ≥9/12 |
| 异常分析 | 6/12 | ≥9/12 |
| 工单幂等 | 9/12 | ≥9/12 |
| 失败边界 | 0/12 | ≥9/12 |

| 时间指标（秒） | 中位数 | P95 | 最大值 |
|---|---|---|---|
| total_seconds | 11.461 | 33.110 | 39.836 |
| model_seconds | 11.323 | 32.932 | 39.599 |
| tool_seconds | 0.006 | 0.021 | 0.026 |

真实模型请求 123 次，独立 Agent run 63 个，工具执行 80 次；包含 A15/A16 案例内部的重复提交。模型请求数与 60 次案例数不同。

token 仅汇总接口实际返回的 usage，超时未返回部分不能记作零消耗；未估算费用。明细见 case-metrics.csv 和 automatic-metrics.json。

## 自动失败清单

| 案例 | 错误码 | 未通过检查 | 原始证据 |
|---|---|---|---|
| A06-1 | NO_DATA | get_device_history_arguments | [A06-1.json](A06-1.json) |
| A06-2 | NO_DATA | get_device_history_arguments | [A06-2.json](A06-2.json) |
| A06-3 | NO_DATA | get_device_history_arguments | [A06-3.json](A06-3.json) |
| A09-1 | MODEL_TIMEOUT | expected_termination, get_device_history_arguments, completed | [A09-1.json](A09-1.json) |
| A09-2 | MODEL_TIMEOUT | expected_termination, get_device_history_arguments, completed | [A09-2.json](A09-2.json) |
| A09-3 | MODEL_TIMEOUT | expected_termination, get_device_history_arguments, completed | [A09-3.json](A09-3.json) |
| A10-1 | MODEL_TIMEOUT | expected_termination, completed | [A10-1.json](A10-1.json) |
| A10-2 | MODEL_TIMEOUT | expected_termination, completed | [A10-2.json](A10-2.json) |
| A10-3 | MODEL_TIMEOUT | expected_termination, completed | [A10-3.json](A10-3.json) |
| A16-1 | MODEL_HTTP_ERROR | expected_termination, completed, reused_order | [A16-1.json](A16-1.json) |
| A16-2 | MODEL_HTTP_ERROR | order_count, expected_termination, create_work_order_arguments, completed, reused_order | [A16-2.json](A16-2.json) |
| A16-3 | MODEL_HTTP_ERROR | order_count, expected_termination, create_work_order_arguments, completed, reused_order | [A16-3.json](A16-3.json) |
| A17-1 | MODEL_HTTP_ERROR | expected_termination, get_device_history_arguments, history_timeout | [A17-1.json](A17-1.json) |
| A17-2 | MODEL_HTTP_ERROR | expected_termination, get_device_history_arguments, history_timeout | [A17-2.json](A17-2.json) |
| A17-3 | MODEL_HTTP_ERROR | expected_termination, get_device_history_arguments, history_timeout | [A17-3.json](A17-3.json) |
| A18-1 | MODEL_HTTP_ERROR | expected_termination | [A18-1.json](A18-1.json) |
| A18-2 | MODEL_HTTP_ERROR | expected_termination | [A18-2.json](A18-2.json) |
| A18-3 | MODEL_HTTP_ERROR | expected_termination | [A18-3.json](A18-3.json) |
| A19-1 | MODEL_HTTP_ERROR | expected_termination | [A19-1.json](A19-1.json) |
| A19-2 | MODEL_HTTP_ERROR | expected_termination | [A19-2.json](A19-2.json) |
| A19-3 | MODEL_HTTP_ERROR | expected_termination | [A19-3.json](A19-3.json) |
| A20-1 | MODEL_HTTP_ERROR | expected_termination, get_fault_guide_arguments | [A20-1.json](A20-1.json) |
| A20-2 | MODEL_HTTP_ERROR | expected_termination, get_fault_guide_arguments | [A20-2.json](A20-2.json) |
| A20-3 | MODEL_HTTP_ERROR | expected_termination, get_fault_guide_arguments | [A20-3.json](A20-3.json) |

## 待真人复核

review-template.json 含 60 条关联原始 SHA256 的待填记录。按 docs/AI_IoT_Agent_验收规则.md 第 5 节逐例复核，填写真实 reviewer、时间、语义成功结论与关键错误；开发 Agent 没有代填。

既定模型 20 秒、工具 3 秒、整轮 90 秒预算未放宽；本轮失败证据保留，不覆盖。
