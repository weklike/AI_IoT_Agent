> 历史快照；当前状态请看 [PROGRESS](../PROGRESS.md)。保留先前失败、取舍和更正，不代表当前结论。

# 开发进度

- 业务基线：v2.0 正式方案已获用户开工授权；v1.1 未调整条款继续回归
- 当前任务：V2-T11 综合验收与交付；T10三页面集成已完成定向验证
- 当前分支/提交：develop@d230b85；第三轮完整真实评测与RSS完整小时在跑，业务代码冻结，文档改动未提交
- 更新时间：2026-09-23T15:48:43+08:00

## 任务状态

下表是v1.1的历史任务状态；本次v2.0方案的当前任务状态见文末。

| 任务 | 状态 | 证据或剩余事项 |
|---|---|---|
| Task 1 骨架与契约 | DONE | 包结构、锁文件、统一 Settings、七表与健康检查 |
| Task 2 模拟器 | DONE | 三独立 MQTT 客户端、三场景、回执；真实 Broker 测试 |
| Task 3 遥测 | DONE | 双唯一约束、严格输入、顺序、新鲜度、重启 unknown |
| Task 4 查询与控制 | DONE | API、完整历史统计、窗口限制、匹配回执及超时 |
| Task 5 工单与幂等 | DONE | 授权、同 run 证据、20 会话并发、原子结果与提交边界 |
| Task 6 Agent | DONE | fixture 协议/预算、真实工具往返及 Docker 网页查询通过；新模型质量另见 Task 9 |
| Task 7 前端 | DONE | 三页面、Markdown 回答；最新 19 项页面测试（含 5 项展示样例）；既有曲线空窗/场景/刷新/错误状态回归通过 |
| Task 8 部署与性能 | DONE | core 后端 153 项 + 最新定向回归；resilience 30 项；60 分钟接收率 100%；最新 API P95 404.300ms |
| Task 9 真实评测与交付 | BLOCKED | gemini-3.8-flash-high 完成 60 次：原判定 51/60，按合同重算 57/60、各类≥9，自动门槛达标；A19 三次模型超时接受为已知限制；真人复核未做，AC-36/38 与 G3 均 PENDING_REVIEW |

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

## 执行结果 Markdown 展示处理

- 原页面以 Vue 文本插值显示模型 Markdown；替换为 MarkdownAnswer.vue + markdown.ts，在前端渲染标题、列表、强调、引用、表格、代码和链接，并保持原始回答与错误状态。
- 使用 markdown-it 15.0.2（固定版本、自带 TS 类型），现有依赖没有同等 Markdown 解析能力。关闭 HTML 执行，限制链接协议并隔离新窗口；图片只显示替代文字。样式限定在回答区域。
- 先复现渲染缺失：4 项失败、普通错误文本 1 项通过；实现后 5 项均通过。首次测试源码转义错误也保留在 red.log，没有将其作为功能缺失证据。

| 实际命令/检查 | 退出码 | 结果 | 证据 |
|---|---|---|---|
| `npm install --save-exact markdown-it@15.0.2`（frontend） | 0 | PASS | package-lock.json；新增 7 包，审计 0 漏洞 |
| `npm --prefix frontend exec -- playwright test -c frontend/playwright.config.ts markdown.spec.ts`（独立 Vite / 定向展示，修改前） | 1 | FAIL | red-rendering/；4 failed / 1 passed |
| 同一定向命令，修改后 | 0 | PASS | green/；5 passed / 7.0s |
| `npm --prefix frontend run typecheck` | 0 | PASS | 无 TypeScript 错误 |
| `npm --prefix frontend run build` | 0 | PASS | build.log；既有 >500kB 警告保留，未提高阈值 |
| `CHARGE_TEST_DEPENDENCY_IMAGE=charge-ops-backend:local npm --prefix frontend run test:e2e` | 0 | PASS | e2e/20260922T114001Z：15 + 1 + 3，共 19 通过，0 skip；隔离资源已清理 |
| 验收镜像静态文件与本地 dist SHA256 比较，标记 local 镜像 | 0 | PASS | image-verification.json；3 文件一致 |
| `docker compose --env-file .env -f deploy/compose.yaml up -d --no-build --no-deps --force-recreate frontend` | 0 | PASS | runtime-after.json；仅前端重建、后端保持 |
| Playwright 读取已保存真实回答，两种分辨率检查 | 0 | PASS | live-after.json/截图；原文一致、3 标题/19 加粗/7 列表，无溢出与脚本错误，模型任务 POST=0 |

- 本轮证据：artifacts/acceptance/markdown-20260922T113519Z；README 已说明刷新即可对已有回答应用新排版。
- 本次只改展示层；后端、prompt、Schema、工具及预算摘要未变，不重跑完整真实评测与 60 分钟性能。旧结果保留且不改变模型成功率结论；新模型完整语义验收仍需后续完成。

## 仓库 clean

- 清理前工作区无未提交修改。按仓库内白名单清理 .pytest_cache、.ruff_cache、业务/测试源码下的 __pycache__、frontend/dist、frontend/node_modules/.vite、生成的 egg-info，以及之前排查留下的 4 个过期临时文件。未使用 git clean/reset 或 Docker prune。
- 删除 120 个文件，文件大小合计 12,518,580 字节（约 11.94 MiB）；du 显示仓库从约 281M 降至 269M。
- 清理前后 705 个 Git 跟踪文件 SHA256 一致；.env、依赖锁、运行中模型转发的 PID/元数据保持一致。保留 .venv、node_modules、运行数据、全部成功/失败验收证据及 Git 历史；没有停止或重建演示容器。

| 实际检查 | 退出码 | 结果 |
|---|---|---|
| Python 白名单清理与逐文件/配置摘要校验 | 0 | PASS；所有选定缓存/临时文件删除，跟踪文件未变 |
| GET `/`、`/api/health` | 0 | PASS；均 HTTP 200，DB/MQTT ready、real |
| `PYTHONDONTWRITEBYTECODE=1 uv run --no-sync python -B` 导入 backend/simulator/tests.support 并查询安装元数据 | 0 | PASS；依赖环境可用，项目版本 0.1.0 |
| `git status --short`、`git diff --exit-code`（更新本条进度前） | 0 | PASS；工作区干净 |

- 仅清理可再生产物，没有业务改动，因此未重跑会再次生成缓存的整套测试。下次前端构建执行 `npm --prefix frontend run build`；开发与测试缓存按需自动重建。

## 导出项目总结与简历描述

- 新增 [项目总结与简历描述](项目总结与简历描述.md)，包含已实现功能、技术栈、技术难点、可直接使用的简历描述及实测数据依据。
- 保留软件模拟/单机演示范围，区分工单服务层 20 并发测试与 Agent 单任务限制；真实模型质量验收未通过，不填写模型准确率。
- 验证：Python 检查文档关键内容与 4 个相对证据链接，退出 0，PASS；纯文档导出，不重跑业务或模型测试。

## 2026-09-22 / AI应用＋物联网扩展方案待审阅

- 用户要求先给开发方案和验收方案，检查完毕后再执行；后续“继续”用于继续本轮方案编写，不视为批准尚未交付的草案。
- 新增 [v2.0开发方案](AI_IoT_Agent_v2.0_开发方案.md) 与 [v2.0验收方案](AI_IoT_Agent_v2.0_验收方案.md)，版本v2.0-draft.1。范围为告警、会话/电量、功率分配、知识检索、主动巡检、证据时间线、工单闭环。
- 给原两份基线文档添加待审阅入口，正文合同保持不变；decisions记录候选取舍。没有修改AGENTS.md、业务代码、依赖锁、运行库、模型配置或常驻服务。
- 开发拆为12项顺序任务；新增XAC-01—60、检索32查询和B01—B24各3次；加上原60次为132次真实案例，均为未来验收要求，不是已执行结果。

### v2.0任务状态

| 任务 | 状态 | 证据或剩余事项 |
|---|---|---|
| V2-T00 批准范围与基线复核 | NOT_STARTED | 先等待用户明确批准草案版本 |
| V2-T01 迁移与操作幂等 | NOT_STARTED | 方案第4、13节 |
| V2-T02 v2遥测与持久化模拟器 | NOT_STARTED | 方案第5、13节 |
| V2-T03 会话与受限控制 | NOT_STARTED | 方案第6、13节 |
| V2-T04 功率分配与反馈 | NOT_STARTED | 方案第7、13节 |
| V2-T05 告警生命周期 | NOT_STARTED | 方案第8、13节 |
| V2-T06 工单处理闭环 | NOT_STARTED | 方案第8、13节 |
| V2-T07 知识资料与检索 | NOT_STARTED | 方案第9、13节 |
| V2-T08 工具、引用与巡检 | NOT_STARTED | 方案第10、13节 |
| V2-T09 时间线与场景脚本 | NOT_STARTED | 方案第11、13节 |
| V2-T10 三页面集成 | NOT_STARTED | 方案第11—13节 |
| V2-T11 综合验收与交付 | NOT_STARTED | 两份方案的最终门槛；仍需真实模型及真人复核 |

### 本轮实际验证

| 实际命令/检查 | 退出码 | 结果 | 证据 |
|---|---|---|---|
| `.venv/bin/python -B -`（内联文档一致性检查，初稿） | 0 | PASS | artifacts/planning/v2.0-draft.1/document-check.json；18项，仅文档 |
| `.venv/bin/python -B -`（修订后重新核对编号、覆盖、链接、格式、阈值、范围与文件摘要） | 0 | PASS | artifacts/planning/v2.0-draft.1/document-check-final.json；18项；XAC60项、B24例、T12项、F7项；原合同除导航说明外逐字保持 |
| `git diff --check` | 0 | PASS | 无空白错误；业务/测试/依赖/AGENTS跟踪文件无差异 |
| 后端/E2E/模型/性能测试 | — | NOT_RUN | 本轮仅方案文档，不重复运行或发起模型请求 |

### 未完成与下一步

- 草案等待用户审阅，不启动实现，不将任何XAC标为PASS。用户可以先审阅开发方案第1节范围、第13节任务与工作量、验收方案第1节完成标准。
- 用户明确确认后，从V2-T00开始；先同步获批的范围变更并核对环境，再运行 `uv run pytest tests/unit/test_agent.py tests/unit/test_eval_summary.py tests/integration/test_agent_workflow.py -q` 复核基线。
- 后续按已批准方案顺序实施到完整验收，不逐任务重复申请继续；真实模型凭据或人工评审缺失时如实记录未完成，完成其他可执行工作。

## 2026-09-22 / 当前模型配置完整 60 次真实评测（v2.0 开工前基线复核）

- 用户决定三项：先用当前模型配置跑完整 60 次；v2.0 新增真实案例集 B01—B24 保持 24 例×3（72 次）；交付目标定为 M4（原 60＋新 72 共 132 例并含真人复核）。v2.0 方案本身仍未批准，未开始任何实现。
- 本轮只执行评测与统计，没有修改业务代码、依赖锁、模型配置、判定逻辑或运行库；新证据写入新目录，历史 Luna 结果原样保留。
- 模型配置：`LLM_MODE=real`、`gemini-3.8-flash-high`、本地 `127.0.0.1:8317/v1`；预算与阈值沿用 Settings 默认值（6 次模型、8 次工具、20/3/90+5 秒）。密钥未进入命令、日志或证据。

### 本次变更
- 无业务代码变更。新增证据目录 `artifacts/acceptance/real-smoke-gemini-20260922T133943Z/`、`artifacts/acceptance/real-model-gemini-20260922T134005Z/`，后者含 60 份案例原件、manifest、automatic-metrics.json、case-metrics.csv、report.md。
- `summarize_automatic.py` 沿用历史同名脚本（逐份校验证据 SHA256 后重算分类统计），复制到本轮目录执行，未修改判定规则。

### 实际验证

| 命令 | 退出码 | 结果 | 证据路径/对应 AC 子项 |
|---|---|---|---|
| `uv run python eval/run.py --mode real --smoke --output artifacts/acceptance/real-smoke-gemini-20260922T133943Z` | 0 | PASS | 2 次模型请求、真实 get_device_status 往返，约 7.3 秒 |
| `uv run python eval/run.py --mode real --repeat 3 --output artifacts/acceptance/real-model-gemini-20260922T134005Z` | 3 | PENDING_REVIEW | 60 份案例原件；自动指标另判 FAIL |
| `uv run python artifacts/acceptance/real-model-gemini-20260922T134005Z/summarize_automatic.py` | 1 | FAIL | automatic-metrics.json；自动 51/60，异常分析 6/12 未达 9/12；60 份证据 SHA256 全部匹配 |
| `uv run python eval/run.py --summarize artifacts/acceptance/real-model-gemini-20260922T134005Z --review-file eval/manual-review.json` | 3 | PENDING_REVIEW | summary.json；没有伪造人工评审 |

### 结果与历史对比

| 项目 | 本轮 gemini-3.8-flash-high | 历史 gpt-5.6-luna |
|---|---|---|
| 自动通过 | 51/60 | 36/60 |
| 分类（状态/历史/异常/工单/边界） | 12/12、12/12、6/12、12/12、9/12 | 12/12、9/12、6/12、9/12、0/12 |
| 模型端 HTTP | 139 次请求，136 次 200，0 次 5xx | 15 次 503 |
| 模型超时 | 3 次（均为 A19） | 6 次 |
| 案例耗时 | 中位 9.69 秒、P95 20.15 秒、最大 22.74 秒 | 另见历史目录 |
| 报告 token | 136 次请求有 usage，合计 254,441（provider 报告值，非账单值） | 另见历史目录 |

- AC-36 仍为 FAIL：51/60 未达 ≥54/60，且异常分析类 6/12 未达 ≥9/12。AC-38/40 仍 PENDING_REVIEW。不因单项改善宣称通过。
- 9 次失败分两种性质：A19 三次是真实模型行为失败（`MODEL_TIMEOUT`，0 次工具调用，model_seconds 20.01—20.02 秒，形态稳定可复现）；A09、A12 各三次只挂在 `get_device_history_arguments` 一条断言上，其余断言全部通过。
- 历史 A06 的空数据流程失败在本轮未复现：A06 三次均正确调用历史工具并按无样本作答。Luna 的 A06 失败原件保留，不改写。

### 未完成与阻塞
- `eval/run.py` 的自动判定对所有含 `get_device_history` 的案例硬编码要求 `window_minutes == 10`。六个相关案例中 A05、A06、A07、A17 的问题文本明写「最近10分钟」，A09、A12 未给任何窗口，v1.1 验收规则对这两例也只要求调用状态/历史/说明并满足语义断言。夹具样本集中在 T0-8 秒内（recovered 档最早 T0-300 秒），10/30/60 分钟窗口返回完全相同的样本，模型取 30/60 分钟不改变可得数据。该冲突影响本轮是否达标，待用户裁决，本轮不改判定、不改证据。
- 真人语义复核与关键错误核对未做，保持 PENDING_REVIEW；不代填 reviewer，不以自动检查替代。

### 下一步
- 用户已决定：判定按合同修正并出重算记录；A19 接受为当前模型配置的已知限制。处理结果见下一节。

## 2026-09-22 / 判定按合同修正与重算记录

- 用户决定两项：`get_device_history_arguments` 按合同修正判定并出一份保留原件的重算记录；A19 的模型超时接受为当前模型配置的已知限制，不放宽 20 秒上限。
- 先写会失败的测试复现问题，再改判定；原始 60 份案例证据、原 `automatic_checks` 结果与 `automatic-metrics.json` 均未修改。

### 本次变更
- `tests/unit/test_eval_summary.py`：新增三项测试——声明窗口的案例必须照用该窗口；未声明窗口的案例接受任意 1—60 分钟整数；未声明窗口仍拒绝越界值、字符串、布尔与错误设备。修改前 `test_undeclared_window_accepts_any_contract_window` 失败，符合预期。
- `eval/cases.jsonl`：给问题文本明写「最近10分钟」的 A05、A06、A07、A17 增加 `history_window_minutes: 10`；A09、A12 不声明，因为问题与验收条目都没有规定窗口。
- `eval/run.py`：`automatic_checks` 改为只在案例声明窗口时校验具体值，未声明时按工具合同校验设备与 1—60 分钟整数，并拒绝额外参数。其余断言不变。
- 新增 `eval/recheck.py`：按当前判定重算已保存轨迹，逐份校验原件 SHA256、比对案例定义是否与执行时一致（只允许新增声明字段）、由唯一 run_id 还原 run_count，输出 `automatic-recheck.json`；已存在同名记录时拒绝覆盖。
- `artifacts/acceptance/results.json`：Luna 的 AC-36/37/38 结论整体移入 `historical_real_evaluations` 并标注被取代，不删除；当前 AC-36/38 改为 PENDING_REVIEW 并指向本轮证据，AC-37 记为 PASS，G3 由 FAIL 改为 PENDING_REVIEW。
- `docs/known-limitations.md`：记录 A19 已知限制与判定修正两条。

### 实际验证

| 命令 | 退出码 | 结果 | 证据路径/对应 AC 子项 |
|---|---|---|---|
| `uv run pytest tests/unit/test_eval_summary.py -q`（修改判定前） | 1 | FAIL | 复现：未声明窗口的案例在窗口 1/10/30/60 下被判不通过 |
| `uv run pytest tests/unit/test_eval_summary.py -q`（修正后） | 0 | PASS | 10 passed |
| `uv run pytest tests/unit -q` | 0 | PASS | 89 passed；判定改动未影响其他单元断言 |
| `uv run python eval/recheck.py --dir artifacts/acceptance/real-model-gemini-20260922T134005Z --note ...` | 0 | PENDING_REVIEW | automatic-recheck.json；57/60，各类≥9，自动门槛达标 |

### 重算结果

| 分类 | 原判定 | 重算 |
|---|---|---|
| 状态查询 A01—A04 | 12/12 | 12/12 |
| 历史统计 A05—A08 | 12/12 | 12/12 |
| 异常分析 A09—A12 | 6/12 | 12/12 |
| 工单幂等 A13—A16 | 12/12 | 12/12 |
| 失败边界 A17—A20 | 9/12 | 9/12 |
| 合计 | 51/60 | 57/60 |

- 改判的恰好是 A09、A12 各三次，且只有 `get_device_history_arguments` 一条断言翻转，其余断言逐条不变；A15/A16 的幂等断言在重算中保持通过，说明由唯一 run_id 还原的 run_count 与执行时一致。
- 仍失败的是 A19 三次 `MODEL_TIMEOUT`，按用户决定记为已知限制，不改判、不放宽超时。
- 自动门槛达标不等于 AC-36 PASS：真人语义复核与关键错误核对仍未进行，AC-36/38 与 G3 保持 PENDING_REVIEW。

### 未完成与阻塞
- 真人逐例语义复核未做（60 例），关键错误计数未知；不代填 reviewer，也不用另一个模型充当人工。
- A19 的安全行为在本轮没有被实际验证到（模型未返回回答），该例证据保留为失败样本。

### 下一步
- 若要推进 G3，需要真人按 `review-template.json` 逐例复核并填 `eval/manual-review.json`，再跑一次 `eval/run.py --summarize`。
- v2.0 方案仍待批准：用户已定 B 集保持 24 例×3、目标 M4，但方案正文的 P0/P1 修订（迁移与 create_all 并存、冷启动知识索引、simulator 状态卷排期、XAC-58/59 重复挂任务、功率计划并行度、start 初始功率与预览有效期）尚未修改，批准前不开始实现。

## 2026-09-22 / v2.0 方案定稿

- 按审阅发现的问题修订两份 v2.0 文档并定稿为正式方案（v2.0，取代 v2.0-draft.1）。范围不变：F01—F07 七项、九工具、三页面、四服务；只改事实陈述、内部矛盾和缺失定义。定稿不等于开工，也不等于任一 XAC 通过。

### 本次变更
- `docs/AI_IoT_Agent_v2.0_开发方案.md`：状态改为正式方案并加 changelog；§1.1 用当前基线评测结论替换过时现状；§1.3 逐条列出待同步的 AGENTS.md 位置；§3 预览有效期 30→120 秒、登记可覆盖的长周期配置、写明本版无鉴权；§4.2 定义迁移为唯一建表路径（停用 `create_all`）并补冷启动自动导入知识索引；§6.1 说明 start 后 0 W 的理由与页面必需文字；§7.1 余量以 100 W 为一份并给出 45,100 W 例；§7.2 预览 120 秒、阶段内并行与最坏耗时 18 秒；§9.1 导入路径统一；§12 补 `GET /station-state`；§11.2 详情页分区与总览聚合查询；§13 重写 V2-T00、状态卷提前到 V2-T02、V2-T08 去掉 XAC-58/59、V2-T11 补窗口判定一致性与 60 分钟负载口径；§15 改为已定事项表。
- `docs/AI_IoT_Agent_v2.0_验收方案.md`：状态与 changelog；§1 补原集当前基线与「已知限制不等于豁免、余量为 0」；§2 拆分 AC-33—34 与 AC-35 映射、修正 AC-36—38 措辞并新增判定口径行；§3.2 预览 120 秒与可覆盖配置白名单；XAC-01/16/20/25/26/41/54 按上述定义补断言；§6 B 集窗口声明规则；§8 补 `eval/recheck.py` 入口；§9 证据目录补重算记录。
- `docs/AI_IoT_Agent_开发计划.md`、`docs/AI_IoT_Agent_验收规则.md`：顶部提示由「待审阅扩展」改为「已定稿、实现未开始」，正文合同未动。

### 实际验证

| 命令 | 退出码 | 结果 | 证据路径 |
|---|---|---|---|
| `.venv/bin/python -B -`（内联文档一致性检查，24 项） | 0 | PASS | artifacts/planning/v2.0/document-check.json；编号完整性、定稿状态、12 处修订落地、阈值与规模未削弱、链接可解析 |
| `git diff --check` | 0 | PASS | 无空白错误 |
| 后端/前端/模型测试 | — | NOT_RUN | 本轮仅文档，不重跑业务或模型 |

### 未完成与下一步
- 等待用户说明开工；开工后从 V2-T00 开始，先同步 AGENTS.md 六处并核对工作区，再按 T01→T11 顺序实施。
- 原案例集的真人语义复核仍未做，AC-36/38 与 G3 保持 PENDING_REVIEW；这是 M4 的硬前置，与 v2.0 实施并行推进。


## v2.0 开工执行（2026-09-22）

用户明确要求按 v2.0 开发方案实施并按配套方案验收，原“等待开工”记录为历史。范围、132 次真实评测及 M4 目标不变。

| 任务 | 状态 | 证据或剩余事项 |
|---|---|---|
| V2-T00 | DONE | 约束同步、历史留存、资源核对，原 164 项回归通过 |
| V2-T01 | DONE | 本地提交 b7208cf；15 项定向、174 项全量通过；XAC-04 仍待全部新 API 接入 |
| V2-T02 | DONE | 1b9194f；93 项相关回归、真实 Broker、子进程及四服务状态卷重启通过 |
| V2-T03 | DONE | 1b9194f；7 项定向、97 项受影响回归通过；分页/统计与5/4秒控制验证 |
| V2-T04 | DONE | daef400；18项相关回归通过（74.92s），真实三设备先降后升及PARTIAL、30秒deadline |
| V2-T05 | DONE | 8d01288；31项遥测/告警回归、52项进一步回归，规则版本、断档、重启unknown |
| V2-T06 | DONE | 8d01288；26项回归，未关闭唯一索引、20独立事务并发、恢复证据与原子流转 |
| V2-T07 | DONE | a37ac94；冻结32条检索通过，20项回归与CLI验证通过 |
| V2-T08 | DONE | 九工具、引用和巡检；73项冻结回归、34项复验、13项控制/会话回归通过 |
| V2-T09 | DONE | 两脚本真实60秒、10项边界回归、24项查询/迁移回归与源表不变检查通过 |
| V2-T10 | DONE | 三页面真实API集成；11项新E2E、5项复查及10次轮询/错误回归通过 |
| V2-T11 | IN_PROGRESS | 综合验收、最终真实评测与人工复核尚待完成 |

### 本次变更
- 原 AGENTS.md 留存 docs/history/AGENTS-v1.1.md；按已批准范围同步条款，两份 v1 文档增加生效说明。
- Database.initialize 停用 create_all，改为校验编号/摘要并在显式事务中迁移；空库与旧库共用路径。新增 v2 ORM/SQL 存储结构，业务功能不据此宣称完成。
- scripts/migrate.py 提供离线检查、备份、升级及新路径恢复；operations.py 在短事务内先查幂等再执行业务回调。
- 保留已有用户修改、评测失败及常驻 deploy 服务；没有修改演示数据库、密钥或模型配置。

### 实际验证
| 命令 | 退出码 | 结果 | 证据 |
|---|---|---|---|
| uv run pytest tests/unit tests/integration -q --junitxml=artifacts/acceptance/v2/start-20260922/baseline.xml | 0 | PASS：164 passed / 286.61s | baseline.xml、baseline.log |
| uv run pytest tests/integration/test_migrations.py -q（实现前） | 1 | FAIL：缺迁移版本记录，3 failed | migrations-red.log |
| uv run pytest tests/integration/test_operations.py -q（实现前） | 1 | FAIL：缺操作幂等模块 | operations-red.log |
| uv run pytest tests/integration/test_migrations.py tests/integration/test_operations.py tests/unit/test_bootstrap.py -q | 0 | PASS：15 passed / 3.16s | t01.xml、t01.log |

证据目录：artifacts/acceptance/v2/start-20260922/。XAC-04 仅基础事务已测，各新 API 未接入，不标整体 PASS。

### 未完成与下一步
- T01 全量回归正在执行；首条检查命令：tail -20 artifacts/acceptance/v2/start-20260922/t01-regression.log。
- T02 起按正式方案顺序继续，不重新询问是否继续。
- 最终 132 次真实评测及真人语义评审尚未执行；历史 A19 失败仍保留，不代表新版本验收通过。

### V2-T01 出口与 T02 进展
- T01 全量：`uv run pytest tests/unit tests/integration -q`，退出 0，174 passed / 308.69s，证据 t01-regression.xml/log。独立 lint 与 git diff --check 通过。仅提交本次迁移相关文件，未把原有评测修改混入提交。
- T02：v1/v2 分别严格校验；v2 UUID 与电量字段参与内容去重；状态返回会话/限制/表底，旧 v1 对应字段为 null。
- 会话报告在提交后 ACK，双唯一键冲突拒绝、终态不回退、不刷新在线；真实 MQTT 定向测试 2 passed / 17.59s。offline 持续报告仍离线：3 passed / 29.81s（t02-report-offline.xml）。
- 模拟器增加 operations 明确模式、整数余数积分、原子 fsync/replace 状态、控制结果与 generation、报告1/2/4/30秒投递和应用ACK。Compose 增加独立 simulator_state 卷；当前默认仍 legacy，完整页面接入前不改变已有演示行为。
- T02 相关回归 93 passed / 83.50s（t02-regression.xml）；重试/积压/磁盘失败 3 passed / 2.24s（t02-delivery.xml）；真实子进程 SIGKILL 后重启 1 passed / 10.88s（t02-process-restart.xml）。
- 四服务容器 SIGKILL/状态卷测试正在执行，尚未记录为 PASS。
- 已发现并先复现修复：被拒绝的高 generation 命令也必须阻挡较低 generation 新命令；应用遥测的 generation 仍仅记录真正应用的命令。失败证据 t02-generation-red.log。

下一步：完成 T02 四服务与协议补充检查；随后 V2-T03 的充电启停 API、命令回执/效果验证、会话查询和统计。当前没有新增页面能力，不声明 M1 或 M4 已通过。

## 2026-09-23 / T03 完成，T04 验证

- 用户“继续”沿用两份 v2.0 方案授权。T02 四服务专用卷 SIGKILL/重启 1 passed /25.06s；T02 最终相关 28 passed /42.79s，证据位于 start-20260922/t02-stack.xml、t02-final.xml。
- T02—T03 保存为本地提交 1b9194f，未推送。T03 启停 request_id/并发/严格参数、5秒超时和晚ACK、4秒效果验证、提交后发布前中断、会话分页与完整统计已实现。
- 发现并复现：查询耗时4.2秒后仍可verified。修复为ACK到达时建立单调deadline，对实际await取剩余4秒预算；失败日志 verification-deadline-red.log 保留。
- T03 定向 7 passed /25.10s（charging-final.xml）；原遥测/历史/工单及充电 97 passed /32.66s（regression.xml）。证据目录 artifacts/acceptance/v2/t03-20260923/。
- T04：allocate_power 8 passed /0.10s；三设备真实MQTT先降后升、无ACK部分失败，以及控制指纹/120秒失效共2 passed /20.74s；固定DataClock且真实单调30秒预算 1 passed /30.65s。初始缺路由/漏导入失败保留为 power-plan-red.log、power-plan.log。
- 功率预览不下发；执行并发分阶段、逐次提升前保守校验上界；确认预算仅在全部verified后更新。stop中止后续提升，未知结果不自动重试或回滚。
- T04 最终相关回归正在执行，不能提前标整组 XAC-23—28 PASS；M1、M4 均未完成。

下一步：核对 t04-regression.xml/log；继续 V2-T05 告警生命周期，再按 T06—T11 顺序推进。

### T05—T06 出口记录
- T04 本地提交 daef400；T05—T06 本地提交 8d01288。无推送或演示库升级。
- T05 通过11项基础、31项告警/遥测/工单、52项迁移/API/Agent回归；证据 alarms.xml、alarms-regression-fixed.xml、t05-regression.xml。一次“乱序”夹具误设为比上一样本更新的时间，保留 FAIL 日志并将输入改为真正旧样本；业务阈值未改。
- 持久化检查点修复：报告投递元数据不推进电量测量时间；8项（含真实进程重启）通过，checkpoint-time-red.log 与 checkpoint-fixed.xml 保留。
- 迁移003为规则/活动告警增加事务内连续观测状态；迁移004把工单唯一范围扩展为全部未关闭状态。编号迁移保持不可修改，旧行未补造会话或电量。
- T06 基础13项、进一步26项通过（9.30s）：IN_PROGRESS/RESOLVED各20个独立服务事务；成功建单指向同一ID；状态迁移失败不留下事件或操作记录；关闭必须满足新鲜状态和关联告警恢复。
- M1/M2及整个版本尚无完整验收结论；任务实现与整项XAC通过不等同。下一步T07，随后T08—T11；最终性能、真实132例及真人评审尚未运行。

### T07 出口记录
- 24篇 authored_simulation 资料，保留旧说明正文和版本。索引和正文原子更新，旧版本可查；失败回滚，health显式不可用。
- 冻结32条检索：FTS5正例24/24、Hit@5=1、MRR@5=1，负例8/8；exact_tags正例23/24、MRR@5=0.7430556，负例8/8。证据 artifacts/acceptance/v2/retrieval-test-20260923-initial/report.json。
- `uv run pytest tests/unit/test_knowledge_index.py tests/integration/test_knowledge_search.py tests/integration/test_migrations.py tests/unit/test_bootstrap.py -q` 退出0，20 passed /3.90s；证据 artifacts/acceptance/v2/t03-20260923/t07-final.xml/log。
- CLI在临时库实跑缺库、待重建、导入、检查及重复导入：退出码2/1/0/0/0；重复导入changed=false，证据同目录t07-cli.json。ruff与diff检查通过。
- 32条查询耗时不是正式200请求性能测试。引用、巡检、页面和最终132次真实模型评测尚未完成，不声明M3/M4。

### T08 实现与当前检查点
- 九工具接入；新五工具只读，授权时9项、未授权时8项。fleet同一时钟/显式SQLite读事务；5,002样本完整统计、空设备保留null；会话/工单展示20条且完整统计不截断。
- KB/DATA引用只接受本run成功工具。9项纯校验及实际检索/跨run引用API测试通过。旧五轮流程与幂等回归37 passed /119.18s（t08-reference-regression.xml）。
- 手动/周期巡检共用单槽位；报告与run/操作幂等原子创建；周期忙碌只留skipped_busy，禁用和重启不补跑。fixture从真实fleet结果生成说明。5项巡检集成通过，含竞争、重复、模型超时、关闭/重启与工具已提交但报告未保存的崩溃窗口（t08-patrol-final.xml）。
- 编号006保存巡检窗口，007增加回执观测/接收时间；时间线SQL投影提前用于第九工具。T09仍需HTTP分页、混合来源完整测试和两个60秒脚本。旧回执缺失的接收时间保持null，不补造。
- t08-checkpoint初轮4项迁移失败：运行时正在新增007，测试读到了不同阶段的迁移集合；保留日志。冻结代码后的完整相关回归正在执行，不能提前记录PASS。当前迁移单独9项通过（t08-migrations-current.xml）。
- 仍未完成T09—T11及最终真人评审；未声明任何完整M阶段通过。

### T08 出口验证
- `t08-frozen-regression.xml/log`：73 passed /125.65s，退出0，包含原五轮流程、20/3/90+5预算、幂等、迁移及新增工具/巡检。
- `t08-ack-times.xml/log`：13 passed /57.22s，退出0，覆盖受影响充电/场景回执和会话接口。
- 出口自查追加两条失败复现（t08-review-red.log）：后续fleet调用不可改变巡检固定窗口；工具时间线事件定义为调用开始，不得用单调耗时补造DataClock接收时间。修复后`t08-reviewed.xml/log`：34 passed /4.04s，退出0；ruff、diff检查通过。
- T08只完成工程范围，不代替M3页面验收或最终B集真实模型评测。T09继续；全版本真人复核仍待执行。

### T09 出口验证
- HTTP时间线支持24小时窗口、稳定游标和源类型计数，分页不截断统计。含12个混合来源事件的测试确认设备隔离、同时间稳定排序、ACK观测/接收时间与全部源表内容不变。修复SQL JSON嵌套被编码为字符串，失败原件t09-timeline-sources-red.log保留。
- 固定脚本名normal_overheat_normal、normal_offline_normal，0/20/40秒发已有场景命令，60秒结束；子命令和步骤关联同事务。取消只停剩余步骤，不暗中恢复场景；手动操作记录MANUAL_SCENARIO_OVERRIDE；重启不续跑，关闭先停脚本再关MQTT。
- 两个60秒脚本在独立Broker/两设备同时实跑：1 passed /65.19s（t09-scripts-real.xml），三步匹配ACK，间隔19—21秒，无device_commands或generation变更。
- 取消/手动覆盖/缺ACK/重启及原场景回归：10 passed /62.28s（t09-boundaries.xml）；时间线/巡检/迁移/启动：24 passed /6.27s（t09-query-final.xml）；源表逐行内容不变：1 passed（t09-replay-immutable.xml）。所有命令退出0，证据位于artifacts/acceptance/v2/t03-20260923/。
- 未升级常驻演示库或推送。T10前端、T11总验收/最终132次真实评测/真人语义复核仍未完成。

### T10 出口验证
- 三页面接入充电/会话、功率预览执行、巡检、知识引用、告警/规则、工单生命周期、时间线和固定脚本；所有展示来自真实API。网络中断与5xx保留原request_id，刷新后可重试；历史与分页有界。fleet补充告警确认事实，确认不等于恢复。
- 隔离operations栈11项新E2E通过（t10-v2-ui-all-initial.log）；后续巡检、断网/5xx、两个尺寸复查5项通过（t10-ui-reviewed.log）。真实停止本次测试模拟器触发PARTIAL，确认预算不变；不操作常驻deploy。1280×720、1920×1080三页面截图存于e2e/20260923T043057Z/operations/。
- 原E2E初轮错误注入仍拦旧接口，已更新到fleet接口；轮询计数初轮把不同device_id/筛选的URL合并，完整重叠URL留证。按实际查询范围分组（移动时间窗保留窗口长度），每查询并发仍要求≤1、离页旧轮询为0，相关两项各重复5次，共10 passed（t10-poll-scope-fixed.log）。失败证据全部保留。原套件其余正常14项、空数据1项、错误3项已通过。
- 后端相关39 passed（t10-backend-regression.xml）；fleet确认字段及列表API复查4 passed（t10-query-reviewed.xml；提交前再次4 passed /1.36s）。typecheck/build、ruff和git diff --check通过；ECharts构建体积警告保留。证据位于artifacts/acceptance/v2/t03-20260923/。
- T10实现不替代完整M阶段验收。T11仍需统一验收入口、B集固定夹具/判定、正式性能与60分钟负载、最终132例真实评测和真人复核。B09窗口文字与通用判定规则冲突已发出澄清，尚未冻结该案例。

### T11 评测入口与查询性能检查点
- 工具超时耗时为null、自动门槛/摘要失败被待评审掩盖的问题先复现4项失败，修复后16项通过（t11-evidence-red.log、t11-evidence-fixed.xml）。自动关键错误不允许藏在成功率余量内，另留红绿证据。
- 全后端检查点278 passed、1 failed /565.11s（t11-backend-checkpoint.xml/log）：旧容器重启测试只设置环境变量，但T10隔离栈改为显式operations参数；改为operations=True后实际四服务SIGKILL/卷恢复1 passed /20.49s（t11-stack-fixed.xml）。未放宽超时/重试或改生产逻辑。
- 新增eval/run_v2.py、元数据驱动判定、隔离会话/功率/告警/工单/知识版本与注入夹具。33项相关验证通过 /7.02s（t11-eval-reviewed.xml）；B21默认3秒超时失败报告、B22两轮独立API/工具与原始消息有实测。B09暂标PENDING_REVIEW，完整72例入口会以NOT_RUN拒绝执行，不私自选择冲突合同。其余案例诊断入口可用；尚未执行正式真实评测。
- 正式新增查询与检索压测：5403行v2遥测、90会话、60告警事件+60工单事件、24资料；预热50、10并发1000请求，各组250。合并P95 384.934ms；fleet 434.551ms、会话138.116ms、统计88.087ms、时间线185.109ms，零错误。检索预热20、固定32查询循环200次，P95 16.462ms，零错误。命令scripts/query_performance_v2.py退出0，证据artifacts/acceptance/v2/query-performance-20260923-initial/。仅覆盖XAC-55这两类子项，不代表整项或60分钟通过。
- 增加仅测试栈使用的只读运行指标包装器；正常create_app没有测试路由、非test拒绝启动，2项验证通过（t11-runtime-monitor.xml）。稳定性脚本正在1分钟诊断，正式60分钟未运行。

- 稳定性1分钟诊断：初轮查询参数直接拼接UTC偏移导致422（stability-smoke-20260923-initial/failure.json），改用httpx params编码并分别保存PUBACK窗口/含10秒排空的提交日志。修复后87/87入库、P95 66.323ms、真实浏览器与资源检查通过（stability-smoke-20260923-fixed/；更严格完整日志/任务检查另存review-current/）。这仅是诊断，不计60分钟验收。
- 最新评测/资源/性能数据夹具相关37 passed /7.66s（t11-harness-final.xml），ruff与diff检查通过。准备保存T11检查点并启动正式60分钟运行。B09合同待澄清，最终132例和真人评审未完成。

## V2-T11 最新验收检查点（2026-09-23 14:38 +08:00）

此节覆盖上文历史续做点；T11仍为IN_PROGRESS，不能推定全部XAC或M4通过。

- 冻结代码：175eba8；24个B案例及知识摘要见 `eval/cases-v2.manifest.json`。B09时间窗口已依照既有“未声明窗口1—60分钟”规则及1/10/60分钟完整会话正向证据解决，B23固定检索问题保留恶意资料负例；不再等待B09澄清。
- 完整后端检查310项通过（`artifacts/acceptance/v2/backend-20260923-reviewed/backend.xml`）；之后数值类型/命令重复矩阵53项、双版本真实MQTT及映射5项通过。计数有重叠，不相加冒充一次全量运行。
- typecheck/build退出0；完整E2E退出0：15常规、1空数据、3错误、11operations，共30项。日志 `artifacts/acceptance/v2/t03-20260923/t11-e2e-all.log`。
- 60分钟operations稳定性退出0：5267/5267唯一PUBACK消息匹配入库，接收率100%，遥测P95 68.249ms；14个报告检查全部通过。原始报告 `artifacts/acceptance/v2/stability-20260923-formal/report.json`。执行源码为e0c9f6a；最终源码中三个文件的兼容理由及前后哈希独立记录，尚须运行证据复核，不将旧源码字节数宣称为最终源码资源测量。
- 正式控制可见性19/20、告警20/20在4秒内；一次4683ms控制样本保留。20次先降后升功率计划全部通过保护上界与35秒终态检查。见 `visibility-20260923-formal/` 和 `power-protection-20260923-formal/`。
- 最终A60/B72真实评测正在同一冻结版本顺序运行。已观察A06三次历史工具缺失，以及A09/A13/A14/A15的MODEL_TIMEOUT；失败原件全部保留，不放宽20秒或改变案例。未完成前不报告最终成功率；真人语义复核仍未执行。
- 当前新增/原查询接口性能复测正在独立Compose环境执行，证据保存至 `query-v2-20260923-final/`、`query-baseline-20260923-final/`。

剩余：完成真实评测及失败根因分析；逐条核对XAC全部子断言；复核稳定性兼容、冷启动与最终复现、来源归属和证据索引；真人语义评审待实际人员填写。原始失败、旧评测和用户现有修改均保留。

### T11 追加核查：资源口径与真实模型（2026-09-23 15:04 +08:00）

- 正式入口结果：iot 120项、ai 69项、resilience 161项全部通过；测试集合重叠，不合计为独立总数。目录分别为 `suite-{iot,ai,resilience}-20260923-final`。
- 原查询P95 414.495ms；新查询综合443.664ms、fleet492.313ms，各组250请求且零错误；知识检索23.601ms。两次独立脚本退出0，见 `query-final-exit-codes.json`。
- 干净归档目录的锁定离线安装、typecheck、build和定向测试全部退出0，见 `clean-reproduction-20260923-final/report.json`。空卷四服务迁移及自动知识检索完成，26.744秒是包含额外15秒观察等待的上界；临时检查误读fleet.status字段导致原FAIL，原件及只读重算说明均保留。
- 新增会话报告12项、控制回执1项、离线告警15秒边界1项、计划并发及最终新鲜度2项通过。真实四服务Broker中断10秒仍持续积分，恢复后权威会话表底差正确，断连窗口没有补造遥测；修正临时测试误用/history路径后通过，原失败保留。
- **更正整项稳定性结论**：首轮脚本14项检查通过，但逐条合同复核发现 Docker MemUsage 不等于进程RSS。首轮5267/5267、68.249ms等实际测量有效；资源断言未覆盖RSS，因此XAC-56仍NOT_RUN（部分断言已PASS），不能沿用前一检查点的整项PASS。新增 `test_stability_resource_contract.py` 已复现缺资源字段仍通过的漏洞；待真实评测冻结结束后修复并重跑完整一小时。新证据不会覆盖首轮。
- 原有 `eval/recheck.py` 有两处验收入口问题：待人工评审返回0、缺3例仍可能满足数值门槛。两个失败测试已复现，待冻结结束后修复；不能拿此入口旧的退出0代替真人结论。
- A集本轮自动44/60，五类12/9/11/2/10，FAIL；B集尚在执行。A06缺历史查询、B06只检索资料未查会话、B16合并引用格式及连续MODEL_TIMEOUT均保留。模型目录端点返回200且模型存在，只证明端点可达，不证明推理延迟合格。

### T11 修复后的验证（b000dee）

- 最终候选01原件完整：A44/60、B46/72，两个入口均退出1。B的自动关键错误包含B15-3越出用户请求目的的建单（授权标志为true，但请求是越界功率控制），不掩盖为普通超时。132条真人复核均未做。
- 通用提示明确：仅历史问题直接查历史；会话/工单状态需对应业务工具；未指定设备先定位；授权不代表要求建单，不能用建单替代不可执行的控制；多个引用分开，不复述旧run标记。
- A06定向3次自动通过；B16/B17/B22各3次自动通过。B06已查询实际会话，但2次错误省略来源ID的KB-前缀，严格引用校验正确阻断。知识工具现在返回由真实source/version/chunk生成的完整citation，模型复制，校验规则未放宽。B06/B15进一步定向运行中；这些诊断不充当最终132例。
- 重算脚本完整案例集与退出码修复，RSS采样修复先红后绿；23项证据/汇总测试通过。新增完整citation先红后绿，引用/Schema/证据相关29项通过。ruff检查及159文件格式检查通过。
- RSS采样使用 `docker top ... -eo pid,ppid,rss,comm`，仅记录PID/父PID/进程名及KiB，不采集命令参数或环境。保留每个进程RSS，不把共享页累加值冒称容器独占内存；Docker CPU/MemUsage仍分别记录。
- RSS一分钟诊断90/90入库、P95 66.574ms，所有资源检查通过；只是诊断。新完整一小时已启动，目录 `stability-rss-20260923-formal`，正式结果未出前XAC-56整项仍未通过。

下一步：查看B06/B15诊断，模型服务可用后固定同一版本重新执行A60/B72；等待RSS完整小时结果；完成逐项证据审计、文档交付与真人复核材料。禁止把候选01原件覆盖或按新prompt重算成新执行结果。

### T11 第二轮结论与最终候选03（d230b85）

- 第二轮A60自动60/60，五类各12；B72自动61/72，各类12/11/6/12/8/12，关键错误0。A退出3待真人，B退出1失败。完整原件及60/72条评审模板保留于 `real-{baseline,v2}-20260923-final-02/`。
- B失败已定位：B11漏读会话；B12把电量窗口归为遥测历史而因NO_DATA提前结束；B17以fleet代替合同要求的单设备status；B08/B18多次补查耗尽预算。修正通用提示的工具职责和足够证据后的停止查询规则，不改变案例、工具参数或判定标准。
- B08/B11/B12/B17/B18新定向各1次自动通过（`real-tool-routing-20260923-diagnostic-03`），25项引用/Schema回归通过；没有以5例代替完整评分。第三轮A60/B72已开始，目录 `real-baseline-20260923-final-03/`、`real-v2-20260923-final-03/`。
- 当前完整后端检查368项通过（638.77秒，`backend-20260923-rss-reference-final.xml`，运行源码b000dee），其后仅改系统提示；新增/扩充边界23项单独通过（`t11-audit-boundaries-final.xml`），计数有重叠不相加。
- 新检查覆盖：停止后不再计量及会话表底隔离；功率槽位竞争、未知上界、阶段间stop、最终stale、重启不重放；会话跨窗口结束语义；知识元数据拒绝；告警旧版本冲突；工单跨设备/过期恢复拒绝及提交成功响应丢失后的原请求恢复。
- 页面知识3项通过（`knowledge-safety-e2e-20260923-verified.log`）：真实来源、实际无命中提示、HTML文本安全。先前无命中预置错误及一次grep无匹配的失败日志保留；未放宽检索验收集。
- RSS完整小时仍运行在b000dee镜像，当前候选唯一运行代码差异是SYSTEM_PROMPT；固定fixture不读取system文本。范围和哈希见 `stability-rss-source-comparison-20260923.json`，结束后按原始日志重新核验。初始3设备同阶段命令发送跨度76.886ms，均早于第一条效果确认，读取证据见 `parallel-phase-20260923.json`。
- 人工复核说明已写入 `docs/real-model-review.md`，尚未伪填任何reviewer或语义结论。完整XAC审计、最终证据索引和交付文档仍在整理，M4未通过。
