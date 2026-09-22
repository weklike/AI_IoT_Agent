# 网页模型超时排查

本次原因是运行中的网页后端未重新加载 .env 模型配置。宿主机独立 smoke 使用 gemini-3.8-flash-high，但网页容器仍使用 gpt-5.6-luna。

| 检查 | 修复前 | 修复后 |
|---|---|---|
| 后端模型 | gpt-5.6-luna | gemini-3.8-flash-high |
| 与 .env 的模型一致性 | 不一致 | 一致；模式、地址、密钥也匹配 |
| 原问题执行 | 首次模型请求 20.001s 超时，工具未执行 | 网页 12.305s 完成，三个工具成功 |
| HTTP/浏览器 | 业务 MODEL_TIMEOUT | 提交 202、轮询 200，无浏览器脚本错误 |

原问题：分析 2 号桩最近 10 分钟的温度，给出排查建议。

仅重新创建 backend 以加载新环境变量；保留数据库、模拟器与 broker，未修改业务源码、提示词或 20/3/90 秒预算。验证前确认没有 queued/running 任务。修复后三次模型请求分别 2.293s、2.388s、6.425s；状态、历史、故障说明工具都 succeeded，未授权建单。

旧失败任务仍保存，浏览器刷新会恢复该任务，不会自动重新请求模型。已验证点击“开始新任务”会清除旧提交并启用输入，验证该操作没有提交新的 Agent 请求。

后续修改 .env 后，执行：

```bash
docker compose --env-file .env -f deploy/compose.yaml up -d --no-build --no-deps --force-recreate --wait --wait-timeout 60 backend
```

独立 eval smoke 只证明该进程加载的配置，不会替网页更新环境。需从网页发起新任务验证；单次成功不代表完整 60 次模型质量评测通过。

证据：before.json、config-after.json、ui-report.json、ui-run.json、run-metrics.json、agent-after.png、old-task-recovery.json。
