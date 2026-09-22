# 开发进度

- 业务基线：v1.1
- 当前任务：Task 6 单 Agent、四工具与模型模式
- 当前分支/提交：develop；Task 1 提交 25792a2；Task 2 已验证待提交，Task 3 测试未提交
- 更新时间：2026-09-22T14:19:50.008162+08:00

## 任务状态
| 任务 | 状态 | 证据或剩余事项 |
|---|---|---|
| Task 1 骨架与契约 | DONE | 54 项单元测试、2 项真实 Broker 健康测试、Compose 三服务 smoke；AC-01 未完成 |
| Task 2 模拟器 | DONE | 5 项单元 + 69 秒真实 Broker 集成通过；三设备 60 秒采样、控制和重启 |
| Task 3 遥测 | DONE | 12 项存储行为 + 2 项真实 Broker 测试通过；页面子项未完成 |
| Task 4 查询与控制 | DONE | API、统计、5000 行限制、回执超时及真实场景链路通过 |
| Task 5 工单与幂等 | DONE | 12 项服务/HTTP 幂等测试通过；模型执行链在 Task 6 集成 |
| Task 6 Agent | BLOCKED | fixture 协议/四工具/预算/默认超时已验证；真实 endpoint/model/key 未配置，未做真实握手 |
| Task 7 前端 | IN_PROGRESS | 三页已实现，6 项真实四服务 E2E 通过；补测交互边界 |
| Task 8 部署与性能 | NOT_STARTED | 待 Task 7 |
| Task 9 真实评测与交付 | NOT_STARTED | 待 Task 8 |

## 本次变更
- 创建 Python/Vue 包、严格遥测合同、统一配置、七表 SQLite、双时钟、健康接口、真实 MQTT 连接、依赖锁及隔离测试资源。
- 模拟器场景与三客户端正在实现。

## 实际验证
| 命令 | 退出码 | 结果 | 证据路径/对应 AC 子项 |
|---|---|---|---|
| `uv python find 3.12` | 2 | BLOCKED | 初始未安装；后续 uv sync 已准备 3.12.13 |
| `uv sync` | 0 | PASS | uv.lock |
| `uv run pytest tests/unit/test_contracts.py tests/unit/test_bootstrap.py -q` | 2 | FAIL | task1/red.txt；实现前模块不存在 |
| 同上 + `--junitxml=artifacts/acceptance/task1/unit.xml` | 0 | PASS | 54 passed；AC-08 输入契约部分、DB 基础 |
| `uv run pytest tests/integration/test_health_mqtt.py -q` | 0 | PASS | task1/mqtt.xml；2 passed |
| `npm --prefix frontend run typecheck` / `run build` | 0 | PASS | 骨架首页 |
| 隔离 `tests.support.resources.stack()` + HTTP 健康/首页检查 | 0 | PASS | task1/smoke.json；仅骨架 smoke |
| `npm --prefix frontend audit`（更新 ECharts 后） | 0 | PASS | 0 vulnerabilities |
| `uv run pytest tests/unit/test_simulator.py -q` | 0 | PASS | task2/unit.xml；5 passed；实现前缺模块失败保存在 task2/red.txt |

## 未完成与阻塞
- 系统 Python 3.13.5，不用于本项目；uv 0.11.3、Node 24.13.0、npm 11.6.2、Docker Compose 5.1.1 / Engine 29.4.0 可用。
- Chromium 1208 缓存存在，尚未实际启动验证。
- 两份基线引用的 `AI_IoT_Agent_方案审阅与修改说明.md` 不存在；实施合同本身完整，暂不阻塞开发。

## 下一步
- 等待 Task 2 真实 Broker 测试；随后实现 Task 3 去重、顺序、新鲜度和 MQTT 消费。

- Task 2 验证：`uv run pytest tests/integration/test_simulator_mqtt.py -q` 退出 0，1 passed / 69.06s；证据 task2/mqtt.xml 与 mqtt-samples.json。AC-03/04/11 的模拟器部分通过，数据库与页面部分未覆盖。

- Task 3：`uv run pytest tests/integration/test_mqtt_ingestion.py -q` 退出 0，2 passed / 17.12s；覆盖真实 MQTT 接收、拒收后可继续、10 次重复投递、Broker 重启后重新订阅和历史保留。证据 task3/mqtt.xml。存储行为 12 passed 见 task3/ingestion.xml。
- 下一步：实现 Task 4 历史窗口/统计、异步场景命令状态、超时与晚到回执；首条验证为 `uv run pytest tests/integration/test_api.py tests/integration/test_scenario_control.py -q`。

- Task 4：API/控制定向测试 10 passed；真实场景测试 4 passed / 25.04s。证据 task4/api.xml、control.xml、openapi.json。首轮测试 UUID 类型赋值警告已修正。全回归结果见 backend-task4.xml。

- Task 5：`uv run pytest tests/integration/test_work_orders.py tests/integration/test_run_idempotency.py -q` 退出 0，12 passed / 2.23s；证据 task5/extended.xml。工单与当前调用结果同事务；20 个独立会话、HTTP 接收并发、回滚、证据与授权检查通过。
- Task 1—4 全回归：87 passed / 118.75s，退出 0，无警告，backend-task4.xml。

- Task 6：默认预算测试 16 passed / 114.99s（task6/default-budgets.xml），包含真实单调 3/20/90 秒；协议单元+快路径 26 passed（task6/fast-final.xml，排除已独立测过的 2 个默认时限测试）。配置脱敏问题先失败后修正。
- Task 7：typecheck/build 通过，6 项 E2E 通过 / 30.8s；e2e/20260922T065554Z 保存截图和 XML。最初占位页的 6 项失败保留于 e2e/20260922T064603Z。
- 实际模型恢复条件：本地 .env 配置 LLM_MODE=real、LLM_BASE_URL（/v1 基地址）、LLM_MODEL、LLM_API_KEY；不能用 fixture 证据代替真实握手和 60 案例评测。
