# 开发进度

- 业务基线：v1.1
- 当前任务：Task 4 查询和场景控制 API
- 当前分支/提交：develop；Task 1 提交 25792a2；Task 2 已验证待提交，Task 3 测试未提交
- 更新时间：2026-09-22T14:19:50.008162+08:00

## 任务状态
| 任务 | 状态 | 证据或剩余事项 |
|---|---|---|
| Task 1 骨架与契约 | DONE | 54 项单元测试、2 项真实 Broker 健康测试、Compose 三服务 smoke；AC-01 未完成 |
| Task 2 模拟器 | DONE | 5 项单元 + 69 秒真实 Broker 集成通过；三设备 60 秒采样、控制和重启 |
| Task 3 遥测 | DONE | 12 项存储行为 + 2 项真实 Broker 测试通过；页面子项未完成 |
| Task 4 查询与控制 | IN_PROGRESS | 已写 API/控制测试，实现前缺模块失败 |
| Task 5 工单与幂等 | NOT_STARTED | 待 Task 4 |
| Task 6 Agent | NOT_STARTED | 待 Task 5 |
| Task 7 前端 | NOT_STARTED | 待 Task 6 |
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
