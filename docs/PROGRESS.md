# 开发进度

- 业务基线：v1.1
- 当前任务：Task 9 网页超时配置问题已修复；后端切换到 gemini-3.8-flash-high，原问题网页复测 12.305s 完成
- 当前分支/提交：develop；本轮排查基线 ff69da5；仅运行配置重载、证据及文档更新，业务源码未改
- 更新时间：2026-09-22T19:26:20+08:00

## 任务状态
| 任务 | 状态 | 证据或剩余事项 |
|---|---|---|
| Task 1 骨架与契约 | DONE | 包结构、锁文件、统一 Settings、七表与健康检查 |
| Task 2 模拟器 | DONE | 三独立 MQTT 客户端、三场景、回执；真实 Broker 测试 |
| Task 3 遥测 | DONE | 双唯一约束、严格输入、顺序、新鲜度、重启 unknown |
| Task 4 查询与控制 | DONE | API、完整历史统计、窗口限制、匹配回执及超时 |
| Task 5 工单与幂等 | DONE | 授权、同 run 证据、20 会话并发、原子结果与提交边界 |
| Task 6 Agent | DONE | fixture 协议/预算、真实工具往返及 Docker 网页查询通过；新模型质量另见 Task 9 |
| Task 7 前端 | DONE | 三页面、14 项 E2E、曲线空窗/窗口切换、离线 16.799s 与恢复 1.353s 均通过 |
| Task 8 部署与性能 | DONE | core 后端 153 项 + 最新定向回归；resilience 30 项；60 分钟接收率 100%；最新 API P95 404.300ms |
| Task 9 真实评测与交付 | BLOCKED | gpt-5.6-luna 完成 60 次：自动 36/60，3 次空数据流程、6 次模型超时、15 次 HTTP 503；未达门槛，真人复核未做 |

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
- 当前 Gemini 的独立 smoke 和网页原问题已通过，完整质量评测尚未执行。此前 gpt-5.6-luna 已通过基础真实工具往返与网页查询；完整 60 次自动检查只有 36 次通过，未达到 ≥54/60。3 次 A06 未执行历史工具、6 次故障分析模型超时、15 次 A16—A20 HTTP 503；结束后的最小请求恢复 200，不能证明稳定。没有回退 fixture 或放宽预算。
- 真实人工语义结论尚无，不能填写 reviewer 或宣布 G3。
- 基线引用的 `AI_IoT_Agent_方案审阅与修改说明.md` 缺失；两份实际业务合同完整，未补造该文档。
- 系统 Python 不作为项目解释器；实际使用 uv 管理 Python 3.12.13、Node 24.13.0、Chromium、Docker Compose 5.1.1；完整环境见证据。

## 下一步
- 独立开发与 fixture 验证已完成；所有测试容器/卷已按所属项目清理；本次按用户要求启动了常驻演示服务（见下方运行记录）。
- AC-01—AC-40 当前索引为 `artifacts/acceptance/results.json`，源码校验为 source-manifest.json。G1/G2 工程证据沿用；AC-36 FAIL（历史 Luna 自动 36/60；当前 Gemini 完整评测 NOT_RUN），AC-37 PASS（完整 60 例时间与 usage 汇总），AC-38/40 PENDING_REVIEW，未声明完整作品交付。
- 本次网页配置问题已解决。后续若继续 G3，以新目录执行当前 Gemini 的完整评测及真人复核，并检查历史 A06 空数据流程失败；修改 prompt/业务逻辑后也需重做完整 60 次。单次接入验证命令：`uv run python eval/run.py --mode real --smoke --output artifacts/acceptance/real-smoke-next-$(date -u +%Y%m%dT%H%M%SZ)`。

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


## 真实模型配置接入与恢复验证

- 用户已保存三个模型配置项；已将本地模式设为 real，并新增仅作用于容器的 LLM_DOCKER_BASE_URL。密钥未进入代码、命令参数或证据。
- 当前演示仍为 http://127.0.0.1:8080；浏览器刷新后显示 real。Docker 通过私有网桥的宿主机转发进程访问原回环模型代理；启动/关闭方式见 README。

| 命令/检查 | 退出码 | 结果 | 证据 |
|---|---|---|---|
| `uv run python eval/run.py --mode real --smoke --output artifacts/acceptance/real-smoke-20260922T094112Z` | 0 | PASS | 两轮真实模型请求，get_device_status，22.388s；只判定工具往返 |
| `uv run pytest tests/unit/test_model_bridge.py -q`（修复前退出断言） | 1 | FAIL | model-bridge-shutdown-red.log；先 wait_closed 导致等待 idle 超时 |
| `uv run pytest tests/unit/test_bootstrap.py tests/unit/test_model_bridge.py -q` | 0 | PASS | real-config-regression.xml；10 passed / 0.61s |
| `docker compose --env-file .env -f deploy/compose.yaml up -d --no-build --no-deps --wait --wait-timeout 60 backend` | 0 | PASS | 后端重新读取配置，health=real，DB/MQTT ready |
| Playwright 提交真实只读设备查询 | 0 | PASS | real-ui-20260922/；实际工具 succeeded、run completed，无浏览器错误 |

- 本轮正式评测命令同上：执行到 12/60 时因反复 20 秒模型请求超时停止做参数诊断，进程收到 SIGINT 后退出 130；保留 12 个案例、manifest 中逐项列出 48 个 NOT_RUN。不是完整验收通过。
- 经修正的程序检查：4 个符合自动条件、8 个 MODEL_TIMEOUT；人工语义结论仍未填写。原 A04 检查过宽导致两次模型超时被标为 automatic_pass，原始文件保留；`automatic-recheck.json` 关联原文件摘要并记录严格重算。
- 单变量 `thinking.type=disabled` 诊断 3 次：2 次 ReadTimeout、1 次 2.129s 成功且 reasoning_tokens=0。仍不足以解决端点不稳定，因此没有将此参数加入生产请求或修改用户选择的模型。
- `uv run pytest tests/unit/test_eval_summary.py tests/unit/test_bootstrap.py tests/unit/test_model_bridge.py -q` 退出 0，17 passed；证据 real-integration-regression.xml。provider 协议回归另 12 passed，real-provider-regression.xml。
- `uv run python eval/run.py --summarize artifacts/acceptance/real-model-20260922T095120Z --review-file eval/manual-review.json` 退出 1，正确报告缺少完整 60 次案例。
- 已向用户说明端点时延问题，等待是否更换模型/服务地址的偏好；当前网页、三设备和真实模式继续运行。


## 更新 .env 后重试 NVIDIA 配置

- 用户切换为 NVIDIA 的 deepseek-ai/deepseek-v4.1-flash。原基地址缺少 /v1，按官方 Chat Completions 路径补全为 https://integrate.api.nvidia.com/v1；其余凭据不回显、不提交。
- 用户已清空 Docker 专用覆盖地址；已重新创建后端读取新模式/模型/地址/密钥，逐项比较确认与本地配置一致。当前直接访问 NVIDIA；关闭了本项目先前创建的 TCP 桥接进程，没有停止用户本机代理。
- 本轮真实 smoke 总耗时 36.880s：第一次模型请求 16.681s 后给出 get_device_status 调用，实际工具成功；第二次请求在 20.021s 触发 MODEL_TIMEOUT，run=timed_out。
- 20/3/90 秒预算、6 次模型/8 次工具上限保持不变，无隐藏重试或 fixture 回退。新一轮完整 60 例未启动，不把单工具成功算作完整回答通过。

| 实际命令/检查 | 退出码 | 结果 | 证据 |
|---|---|---|---|
| `uv run python eval/run.py --mode real --smoke --output artifacts/acceptance/real-smoke-nvidia-20260922T102833Z` | 1 | FAIL | manifest.json、A01-1.json；最终回答请求 MODEL_TIMEOUT |
| `docker compose --env-file .env -f deploy/compose.yaml up -d --no-build --no-deps --wait --wait-timeout 60 backend` | 0 | PASS | 后端 healthy，已匹配新配置 |
| 宿主机及容器读取 /v1/models（不打印认证头） | 0 | PASS | HTTP 200，配置模型存在；container-check.json |
| `curl --silent --show-error http://127.0.0.1:8080/api/health` | 0 | PASS | DB/MQTT ready、real |

- 下一步：在既定 20 秒单次上限内获得完整工具往返成功，再使用新证据目录执行 60 例；若修改时限合同需单独记录范围变化，不能把放宽后的结果当成原合同通过。


## 更换 gpt-5.6-luna 后重新测试

- 新配置使用本机回环代理。重新启动本项目的私有网桥 TCP 转发，并仅设置本地 Docker 地址覆盖，保留用户模型名、宿主机地址及密钥。后端已重建，四项模型配置逐一比较一致，DB/MQTT ready、模式 real。
- 所有业务源码、prompt、Schema、评测逻辑与依赖锁摘要均和已有源码证据一致；本次仅重载配置与执行新模型测试。旧模型效果结论不沿用。

| 实际命令/检查 | 退出码 | 结果 | 证据 |
|---|---|---|---|
| `uv run python eval/run.py --mode real --smoke --output artifacts/acceptance/real-smoke-luna-20260922T103822Z` | 0 | PASS | 两次模型请求、真实 get_device_status、最终回答；7.778s |
| `docker compose --env-file .env -f deploy/compose.yaml up -d --no-build --no-deps --wait --wait-timeout 60 backend` | 0 | PASS | container-check.json；配置匹配，DB/MQTT ready、real |
| Playwright 提交真实只读设备查询 | 0 | PASS | real-ui-luna-20260922/report.json、agent.png；18.308s，无浏览器错误 |
| `uv run python eval/run.py --mode real --repeat 3 --output artifacts/acceptance/real-model-luna-20260922T104501Z` | 3 | PENDING_REVIEW | 60 次均有原始轨迹；入口等待真人，自动指标另判 FAIL：36/60，未达 ≥54/60 |
| `uv run python artifacts/acceptance/real-model-luna-20260922T104501Z/summarize_automatic.py` | 1 | FAIL | 完整样本自动门槛未通过；automatic-metrics.json、case-metrics.csv、report.md；60 个证据 SHA256 全部匹配 |
| `uv run python eval/run.py --summarize artifacts/acceptance/real-model-luna-20260922T104501Z --review-file eval/manual-review.json` | 3 | PENDING_REVIEW | human-summary.log；没有伪造人工评审 |
| 模型列表 + 单次最小 Chat 请求诊断 | 0 | PASS | endpoint-diagnostic.json；列表 200 且模型存在，最小请求 200 / 2.550s，仅证明当时恢复 |

- 分类自动检查：状态查询 12/12、历史统计 9/12、异常分析 6/12、工单幂等 9/12、失败边界 0/12。A17—A20 被 HTTP 503 阻断，不能据此声称验证了其安全行为。
- 总计 60 次案例、63 个独立 Agent run、123 次模型请求、80 次工具调用；完整保留失败分母。A15 同 request_id 三次均复用原 run/工单，A16 新 request_id 组遭遇 503，未通过。
- 案例总耗时中位数 11.461s / P95 33.110s / 最大 39.836s；含所有快速失败和多 run 案例。99 次请求返回 usage，共 126019 token；24 次失败请求缺 usage，不将其计作零费用，不估算本机代理价格。
- 60 条真人复核模板已生成，reviewer/语义结果/关键错误数仍未知。未修改业务源码或 prompt，不改演示库，不提高 20/3/90 秒预算。此前 DeepSeek/NVIDIA 失败原样保留。

## 新 API 仅执行一次测试

- 用户明确要求只进行一次测试。本次读取最新 .env，模型为 gemini-3.8-flash-high；将本机代理基地址补上此前使用的 /v1，模型名和密钥保持原样。
- 仅执行 A01 一次：两次模型请求完成“请求状态工具 → 实际 get_device_status → 最终回答”，总耗时 6.373s，run=completed、无错误。两次模型请求分别为 2.700s、3.497s；一次案例不等于一次 HTTP 请求。
- 没有额外模型探测或自动重试，没有执行 60 次评测。使用独立临时库；没有重载常驻网页后端，不宣称网页已经切换到新配置。没有修改业务源码或提示词。

| 实际命令/检查 | 退出码 | 结果 | 证据 |
|---|---|---|---|
| `uv run python eval/run.py --mode real --smoke --output artifacts/acceptance/real-smoke-api-once-20260922T111351Z` | 0 | PASS | manifest.json、A01-1.json、report.json；仅真实工具协议往返 |
| 单次执行数量、证据 SHA256 与本次密钥泄漏检查 | 0 | PASS | 一个案例、一个 run、两次模型请求；原始证据摘要一致，未包含本次密钥 |

- 本次请求已完成。历史完整评测失败保留，G3 未通过；新配置未执行完整评测及真人语义复核。

## 网页超时：后端未加载新模型配置

- 从实际开发库只读查询用户最近失败任务：问题为“分析 2 号桩最近 10 分钟的温度，给出排查建议。”，首次模型请求 20.001s 后 MODEL_TIMEOUT，尚无工具调用。
- 对比容器环境与本地 .env（不输出密钥）：运行模型仍 gpt-5.6-luna，本地已 gemini-3.8-flash-high；模式、Docker 地址、密钥一致。上次独立 smoke 未重载网页容器。
- 确认当前没有 queued/running 任务后，仅重新创建 backend 加载最新配置，保留数据卷、MQTT 与模拟器。四项配置随后全部匹配，DB/MQTT ready、real。

| 实际命令/检查 | 退出码 | 结果 | 证据 |
|---|---|---|---|
| 只读任务查询与容器/.env 一致性检查 | 0 | FAIL | before.json；LLM_MODEL 不一致，实际失败任务 20.001s |
| `docker compose --env-file .env -f deploy/compose.yaml up -d --no-build --no-deps --force-recreate --wait --wait-timeout 60 backend` | 0 | PASS | config-after.json；四项匹配、健康 |
| Playwright 网页提交用户相同问题 | 0 | PASS | ui-report.json、ui-run.json、agent-after.png；12.305s completed，三工具成功，无浏览器错误 |
| 只读查询新任务的模型耗时 | 0 | PASS | run-metrics.json；2.293s、2.388s、6.425s，均在单次 20s 内 |
| Playwright 恢复旧失败任务后点击“开始新任务” | 0 | PASS | old-task-recovery.json；旧提交清除，输入恢复，额外 Agent POST=0 |

- 本轮证据目录：artifacts/acceptance/web-timeout-20260922T112100Z。README 已补充 .env 更新后的容器加载命令和旧任务恢复说明。
- 本次未改业务代码、prompt、Schema 或时限，不需重跑无关测试；未执行完整 60 次评测，新模型质量与人工复核仍未完成。旧失败保留。
