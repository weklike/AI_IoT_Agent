# gpt-5.6-luna 真实模型重测

共完成 60 次案例执行，自动检查通过 51/60；总体状态 FAIL。人工语义与关键错误复核尚未执行，不能把自动通过数称为最终成功数。

模型及参数、prompt/Schema 摘要见 manifest.json；原始案例未修改。每例隔离临时库，未向演示库写入测试工单。

| 类别 | 自动通过 / 执行数 | 门槛 |
|---|---|---|
| 状态查询 | 12/12 | ≥9/12 |
| 历史统计 | 12/12 | ≥9/12 |
| 异常分析 | 6/12 | ≥9/12 |
| 工单幂等 | 12/12 | ≥9/12 |
| 失败边界 | 9/12 | ≥9/12 |

| 时间指标（秒） | 中位数 | P95 | 最大值 |
|---|---|---|---|
| total_seconds | 9.694 | 20.151 | 22.740 |
| model_seconds | 9.544 | 20.022 | 22.493 |
| tool_seconds | 0.008 | 0.031 | 0.049 |

真实模型请求 139 次，独立 Agent run 63 个，工具执行 124 次；包含 A15/A16 案例内部的重复提交。模型请求数与 60 次案例数不同。

token 仅汇总接口实际返回的 usage，超时未返回部分不能记作零消耗；未估算费用。明细见 case-metrics.csv 和 automatic-metrics.json。

## 自动失败清单

| 案例 | 错误码 | 未通过检查 | 原始证据 |
|---|---|---|---|
| A09-1 | 无运行错误码 | get_device_history_arguments | [A09-1.json](A09-1.json) |
| A09-2 | 无运行错误码 | get_device_history_arguments | [A09-2.json](A09-2.json) |
| A09-3 | 无运行错误码 | get_device_history_arguments | [A09-3.json](A09-3.json) |
| A12-1 | 无运行错误码 | get_device_history_arguments | [A12-1.json](A12-1.json) |
| A12-2 | 无运行错误码 | get_device_history_arguments | [A12-2.json](A12-2.json) |
| A12-3 | 无运行错误码 | get_device_history_arguments | [A12-3.json](A12-3.json) |
| A19-1 | MODEL_TIMEOUT | expected_termination | [A19-1.json](A19-1.json) |
| A19-2 | MODEL_TIMEOUT | expected_termination | [A19-2.json](A19-2.json) |
| A19-3 | MODEL_TIMEOUT | expected_termination | [A19-3.json](A19-3.json) |

## 待真人复核

review-template.json 含 60 条关联原始 SHA256 的待填记录。按 docs/AI_IoT_Agent_验收规则.md 第 5 节逐例复核，填写真实 reviewer、时间、语义成功结论与关键错误；开发 Agent 没有代填。

既定模型 20 秒、工具 3 秒、整轮 90 秒预算未放宽；本轮失败证据保留，不覆盖。
