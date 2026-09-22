# 开发进度

- 业务基线：v1.1
- 当前任务：Task 9 等待真实模型配置与人工复核；G1/G2 已通过，G3 BLOCKED
- 当前分支/提交：develop；实现提交 75c3c33，验收截图修复 2d066f1；后续提交仅更新文档与证据
- 更新时间：2026-09-22T17:36:10+08:00

## 任务状态
| 任务 | 状态 | 证据或剩余事项 |
|---|---|---|
| Task 1 骨架与契约 | DONE | 包结构、锁文件、统一 Settings、七表与健康检查 |
| Task 2 模拟器 | DONE | 三独立 MQTT 客户端、三场景、回执；真实 Broker 测试 |
| Task 3 遥测 | DONE | 双唯一约束、严格输入、顺序、新鲜度、重启 unknown |
| Task 4 查询与控制 | DONE | API、完整历史统计、窗口限制、匹配回执及超时 |
| Task 5 工单与幂等 | DONE | 授权、同 run 证据、20 会话并发、原子结果与提交边界 |
| Task 6 Agent | BLOCKED | fixture 与协议/预算实现完成；真实 endpoint/model/key 缺失 |
| Task 7 前端 | DONE | 三页面、14 项 E2E、曲线空窗/窗口切换、离线 16.799s 与恢复 1.353s 均通过 |
| Task 8 部署与性能 | DONE | core 后端 153 项 + 最新定向回归；resilience 30 项；60 分钟接收率 100%；最新 API P95 404.300ms |
| Task 9 真实评测与交付 | BLOCKED | 20 案例入口、人工汇总与材料已实现；真实 60 次评测及人工复核未完成 |

## 本次变更
- 从仅有方案的目录初始化现有项目，按九任务顺序实现；没有创建平行项目或修改全局配置。
- Agent 保存完整消息、工具配对、调用顺序、错误轨迹；持久化重启遗留任务与场景终态。
- 三页面使用真实 API，刷新恢复任务，网络重试复用 request_id，离开页面取消请求和轮询。
- 验收脚本使用独立 Compose 项目、随机端口、临时卷；真实模型与人工评审均不以 fixture 替代。
- 历史接口标记缺报空窗，图表断线；查询性能通过实际压测定位，不放宽阈值。

## 实际验证
所有路径相对 `artifacts/acceptance/`；失败/初轮结果保留。

| 命令 | 退出码 | 结果 | 证据路径/对应 AC 子项 |
|---|---|---|---|
| `uv sync --locked` / `npm --prefix frontend ci` | 0 | PASS | uv.lock、package-lock.json、npm-ci.log |
| `uv run python scripts/acceptance.py --suite core --output artifacts/acceptance/core-final` | 0 | PASS | core-final/；153 passed / 325.92s；后端自动子断言与四服务冷启动 12.74s |
| `npm --prefix frontend run typecheck` / `run build` | 0 | PASS | 构建完成，图表 bundle 体积警告保留 |
| `npm --prefix frontend run test:e2e` | 0 | PASS | e2e/20260922T075908Z；10 常规 + 1 空数据 + 3 故障 |
| `uv run pytest tests/integration/test_api.py -q` | 0 | PASS | history-gap-fixed.xml；8 passed；空窗不补造样本 |
| `uv run python scripts/acceptance.py --suite performance --output artifacts/acceptance/performance-20260922` | 1 | FAIL | 3600s、5391/5391 PUBACK 入库、遥测 P95 79.497ms；API P95 650.164ms 超过 500ms |
| `uv run python scripts/query_performance.py --output artifacts/acceptance/api-reproduction` | 1 | FAIL | 5403 条预置数据，50 预热/10 并发/1000 请求，P95 624.129ms，无错误 |
| `uv run python eval/run.py --mode fixture --repeat 3 --output artifacts/acceptance/fixture-eval-reviewed` | 3 | PENDING_REVIEW | 60 次实际 API/工具/DB，57 次结构断言通过，A06 三次失败；不是模型效果验收 |
| `uv run python eval/run.py --mode real --repeat 3 --output artifacts/acceptance/real-model-initial` | 2 | BLOCKED | 配置缺失，实际执行 0 个真实案例 |

| `uv run python scripts/query_performance.py --output artifacts/acceptance/api-projection`（同锁依赖缓存） | 0 | PASS | 5403 条，50/10/1000，P95 404.300ms，零错误 |
| `uv run pytest tests/integration/test_api.py tests/integration/test_work_orders.py -q` | 0 | PASS | history-projection.xml；20 passed |
| `uv run pytest tests/integration/test_api.py tests/integration/test_agent_workflow.py tests/integration/test_run_idempotency.py -q` | 0 | PASS | api-serialization-fixed.xml；35 passed；服务层另 24 passed |
| `npm --prefix frontend run test:e2e`（新曲线/窗口/时限） | 0 | PASS | e2e/20260922T084330Z；14 项；e2e-timing-evidence 精确时限 JSON |
| `uv run python scripts/acceptance.py --suite performance --reuse-performance artifacts/acceptance/performance-20260922 --query-evidence artifacts/acceptance/api-projection --output artifacts/acceptance/performance-final` | 0 | PASS | performance-final/report.json；沿用范围与变更见 performance-compatibility.json |
| `uv run python scripts/acceptance.py --suite resilience --reuse-performance artifacts/acceptance/performance-20260922 --query-evidence artifacts/acceptance/api-projection --output artifacts/acceptance/resilience-final` | 0 | PASS | 30 passed / 174.32s；resilience-final/report.json |
| `uv run ruff check backend simulator tests scripts eval` / `ruff format --check ...` | 0 | PASS | 61 文件；无 lint/格式错误 |

| 干净临时 checkout：`uv sync --locked --offline`、`npm --prefix frontend ci --offline`、typecheck/build、隔离四服务启动与错误截图 | 0 | PASS | clean-reproduction-copy/report.json；初次跨文件系统硬链接失败保留，改用 --no-hardlinks |
| `cold_start()` 独立四服务及浏览器截图复验 | 0 | PASS | cold-start-capture/report.json；10.661s，browser-final.png；旧信号收尾截图错误见 decisions |

## 未完成与阻塞
- 初轮 API 性能失败已经修复；原 FAIL 保留，新样本见 api-projection。PyPI 两次构建超时已使用相同锁文件镜像依赖缓存恢复，未改变业务依赖。
- real 需要本地配置 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY 和 LLM_MODE=real。不要将凭据放进命令参数或评测证据；没有经验证 endpoint/model，不能声明 real 可用。
- 真实人工语义结论尚无，不能填写 reviewer 或宣布 G3。
- 基线引用的 `AI_IoT_Agent_方案审阅与修改说明.md` 缺失；两份实际业务合同完整，未补造该文档。
- 系统 Python 不作为项目解释器；实际使用 uv 管理 Python 3.12.13、Node 24.13.0、Chromium、Docker Compose 5.1.1；完整环境见证据。

## 下一步
- 独立开发与 fixture 验证已完成；所有测试容器/卷已按所属项目清理；本次按用户要求启动了常驻演示服务（见下方运行记录）。
- AC-01—AC-40 当前索引为 `artifacts/acceptance/results.json`，源码校验为 source-manifest.json。G1/G2 PASS；AC-36/37 BLOCKED，AC-38/40 PENDING_REVIEW，未声明完整作品交付。
- 本地真实模型配置就绪后先 `uv run python eval/run.py --mode real --smoke --output artifacts/acceptance/real-smoke-01`；成功再执行完整 60 次与真人复核。

- 真人完成 60 例语义/关键错误复核并填写 eval/manual-review.json 后运行 summarize；按 docs/demo.md 完成个人 3—5 分钟演示，确认能解释代码和简历数字。不得由开发 Agent 冒充真人完成。


## 2026-09-22 17:35 / 启动界面

- 按用户要求启动本机四服务，Compose 项目 `deploy`，数据卷 `deploy_backend_data` 保留运行；网页 http://127.0.0.1:8080，端口均只绑定 127.0.0.1。
- 核对源码摘要后，将当前已验收缓存镜像 `test-0dd90077e597f20f` 标记为本地演示镜像；使用正常 create_app/模拟器入口，没有加载测试失败替身、预置评测数据或修改 .env。
- 仅检查配置是否存在：本地 .env 与当前进程中 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY 都为空，LLM_MODE=fixture。没有打印任何密钥值。真实接入仍需指定服务及本地凭据。

| 实际命令/检查 | 退出码 | 结果 | 证据 |
|---|---|---|---|
| `docker compose --env-file .env -f deploy/compose.yaml up -d --no-build --wait --wait-timeout 120` | 0 | PASS | 四服务 running；backend/mqtt healthy |
| `curl --silent --show-error http://127.0.0.1:8080/api/health` | 0 | PASS | DB/MQTT ready，llm_mode=fixture |
| Node Playwright 访问 /devices、/devices/CHG-002、/agent 并截图 | 0 | PASS | artifacts/acceptance/demo-start-20260922/report.json；三设备在线且数据新鲜，无脚本错误或横向溢出 |
| `xdg-open http://127.0.0.1:8080` | 3 | BLOCKED | 此 WSL 环境无桌面浏览器启动器；网页服务与 headless Chromium 检查正常，可从宿主机点击 URL |

- 下一步：用户确定模型服务，在本地 .env 填入模型配置，再验证真实工具调用往返；现有 fixture 演示继续运行。
