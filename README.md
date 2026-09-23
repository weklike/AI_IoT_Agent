# 充电设备监控与运维 Agent

三台独立 MQTT 软件设备、FastAPI 单体、SQLite、Vue 三页，以及一个有九项进程内业务工具的运维 Agent。v2.0 增加软件充电会话与计量、站点功率分配、告警及工单生命周期、版本化 FTS5 知识检索、只读巡检与事件复盘。设备启停和功率控制由页面调用受限 API；Agent 只有查询及明确授权后的建单能力。

**当前处于 v2.0 综合验收，尚未通过 M4。** T01—T10 已实现并完成定向验证；正式查询压测及含进程RSS的60分钟稳定性已通过；最终原60＋新增72次真实模型评测仍在执行，真人复核尚未完成。`fixture` 只替换模型响应，业务工具、数据库与副作用仍为真实实现，不能作为模型效果成绩。当前状态见 [PROGRESS](docs/PROGRESS.md)与[逐项验收核对](docs/acceptance-v2-audit.md)，历史 v1 证据单独保留，不当作本版完整验收结论。

![v2设备总览](artifacts/acceptance/e2e/20260923T062547Z/operations/layout_v2--v2-three-page-layout-1280/设备总览-1280.png)

## 环境与启动

Linux/WSL2 + Docker Compose，源码与 SQLite 位于 Linux 本地文件系统。需要 uv 和 Node.js ≥22.12。本项目锁定 Python 3.12；首次 `uv sync` 会按需准备解释器。已验证的工具版本与依赖见 [设计记录](docs/decisions.md)、`uv.lock`、`frontend/package-lock.json`。

```bash
# 从仓库根目录；已有配置不覆盖
[ -e .env ] || cp .env.example .env
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend exec -- playwright install chromium
# 仅当浏览器缺少系统库时，由管理员准备：
# npm --prefix frontend exec -- playwright install-deps chromium

SIMULATOR_MODE=operations docker compose --env-file .env -f deploy/compose.yaml up -d --build
```

打开 **http://127.0.0.1:8080**。只绑定本机端口：前端 8080、后端 8000、MQTT 1883。`/api/health` 返回 DB/MQTT 依赖状态与模型模式；依赖未就绪为 503。界面用中文文字显示 online/offline、unknown、过温与数据过期。

容器数据库位于 backend 独立卷；本机调试使用 `data/charge_ops.db`，二者不共用。关闭演示服务使用 `docker compose --env-file .env -f deploy/compose.yaml down`，不带 `-v` 保留数据。不要用删除开发库来运行测试。

## 运行模式与旧库升级

新建演示使用 `SIMULATOR_MODE=operations`：初始空闲、0W；启动会话只登记请求功率，实际限制仍为0W，随后在总览预览并执行站点功率计划。`legacy` 保留原固定20kW采样，仅用于原协议回归；不能在该模式演示v2充电控制。现有 `.env` 不会被安装命令覆盖。

backend 使用 `/data` 数据卷，simulator 使用独立 `/simulator-state` 检查点卷。模拟器重启会把旧活动会话标为 `INTERRUPTED/SIMULATOR_RESTART`，保留持久化电量与未知区间，不补算停机能量。不要同时启动宿主机与容器来写同一个 SQLite 文件或模拟器检查点目录。

既有数据库升级前停止它的写入进程并备份。下面命令针对**宿主机指定库**；不要把路径改成用户正在运行的其他库。容器库应在停止所属服务后取出一致副本，先在新路径验证升级与恢复，再进行维护切换。

```bash
uv run python scripts/migrate.py --check --database data/charge_ops.db
# 每次使用新的备份目录；运行库会被拒绝，原备份不可覆盖
uv run python scripts/migrate.py --apply --database data/charge_ops.db --backup-dir artifacts/backups/v2-upgrade-01
# 需要回退时恢复到新路径，保留升级后的原库
uv run python scripts/migrate.py --restore artifacts/backups/v2-upgrade-01/database.sqlite3 --destination data/restored-v1.db
```

迁移以编号SQL和SHA256校验为唯一建表路径，不使用 `create_all`。FTS5缺失或索引失败会明确报告不可用，不能把它显示为“没有知识命中”。

## 本机开发

先启动自己的 Broker（或仅启动 Compose mqtt 服务），再运行：

```bash
uv run uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
npm --prefix frontend run dev
```

前端开发代理 `/api` 到 127.0.0.1:8000。生产页面由 nginx 同源代理后端。首次空库依次执行编号迁移、初始化三设备、按摘要导入24篇知识，不需要手动补表或索引；可选的 `uv run python scripts/seed_demo.py --profile demo` 只初始化空库，不重置现有数据。

## 操作闭环

1. 总览查看三台设备与样本时间，进入 CHG-002 详情。
2. 点击“模拟过温”，等待匹配回执和新样本；发布成功不会提前显示 applied。
3. Agent 中查询状态或分析历史。未勾选授权时不暴露写工具，服务器仍会再次检查。
4. 需要建单时开始新任务，勾选授权并明确提出建单要求。工单必须基于本任务、本设备的有效只读证据。
5. 刷新恢复原 run；网络提交失败可复用原 request_id 重试。新任务再次建同设备同原因工单，复用已有未关闭工单编号（OPEN/IN_PROGRESS/RESOLVED）。
6. “暂停上报”保留控制订阅。数据超过 10 秒先过期，最后新鲜接收超过 15 秒才离线；恢复 normal 后用新样本确认在线。

## v2 页面闭环

- 详情页启动/停止软件充电会话；核对 pending、applied、verified/unconfirmed、原始会话报告与整数Wh。会话统计明确区分“窗口内结束的完整会话电量”和自然时间窗口耗电。
- 总览预览 equal/priority 分配后再执行；预览120秒有效且受控制状态指纹约束。先降低并验证，再提高；PARTIAL保留已确认/未知部分，确认预算只在全部目标verified后改变。
- 告警“确认”只表示已查看；过温恢复需要低于55°C连续10秒新鲜样本。工单按OPEN→IN_PROGRESS→RESOLVED→CLOSED处理，关闭由服务器重查当前恢复及关联告警。
- 一键巡检始终只读，和对话共享一个运行槽位；定时巡检默认关闭，启用后30分钟一次，忙碌留skipped_busy，不排队补跑。
- 知识来源卡片展示实际source/version/chunk；`[DATA:…]`只对应当前run成功工具。24篇资料为项目自写的模拟系统说明，FTS5不是向量RAG。
- 时间线只读复盘真实记录；两个60秒场景脚本通过原场景命令和ACK运行，取消不自动恢复场景，也不偷偷操作充电或控制generation。

## 自动化验证

测试拥有独立临时 SQLite、Compose 项目、卷、随机端口、MQTT 前缀与客户端 ID，只清理自身资源。同源代码测试可复用只读镜像缓存，不复用业务数据。E2E 的空数据和失败环境使用独立实例；超时替身仅存在于 `tests/support/failure_app.py`，不能进入正常 real 路径。

```bash
uv run pytest tests/unit tests/integration -q --junitxml=artifacts/acceptance/backend.xml
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run test:e2e

# 每次用新目录，避免覆盖失败证据
ACCEPTANCE_STAMP=$(date -u +%Y%m%dT%H%M%SZ)
uv run python scripts/acceptance.py --suite core --output "artifacts/acceptance/core-$ACCEPTANCE_STAMP"
uv run python scripts/acceptance.py --suite performance --output "artifacts/acceptance/performance-$ACCEPTANCE_STAMP"
uv run python scripts/acceptance.py --suite resilience --output "artifacts/acceptance/resilience-$ACCEPTANCE_STAMP"
```

`core` 执行后端契约测试和独立四服务冷启动，并按 AC 编号列出自动化子项；页面与人工子项在总索引中单独合并。`performance` 真实运行 60 分钟，保持浏览器打开，按 PUBACK ID 与历史样本核对接收率，读取事务返回后的提交日志计算延迟，然后预热 50 次、10 并发发送 1000 次本地查询。不能缩短时长后仍称通过。

`resilience` 执行重启/依赖恢复与 Agent 中断测试，并运行 60 分钟稳态检查。若已有相容的完整性能证据，可传 `--reuse-performance <原始证据目录>`，报告保留原始摘要与来源；必须说明版本相容性，不能拿旧数据掩盖行为变更。仅复测查询可运行 `uv run python scripts/query_performance.py --output <新目录>`（三设备 60 分钟预置数据）；汇总时用 `--query-evidence <查询目录>` 独立引用新样本，保留原失败。当前沿用依据见 `artifacts/acceptance/performance-compatibility.json`。

自定义入口退出码：0=通过，1=验收失败，2=环境阻塞，3=待人工复核。pytest/npm 保留自身退出码。尚未覆盖的 AC 子项仍为 NOT_RUN；测试数量不是验收通过率。若外网下载不可用，可显式设置 `CHARGE_TEST_DEPENDENCY_IMAGE=<已有测试镜像>`；工具先核对 uv.lock/pyproject 完全相同，再复制当前源码、离线安装，不能复用旧业务数据。

## 回答显示

Agent 执行结果支持 Markdown 标题、列表、强调、引用、表格与代码块，已有回答刷新页面后即可应用排版。宽表格和代码在回答区内滚动。模型原始 HTML 按文本展示，图片保留替代文字，链接只接受安全协议。渲染采用 markdown-it 15.0.2（MIT）；原始回答与工具轨迹仍由后端保存。

## 真实模型与评测

只在本机 `.env` 配置 `LLM_BASE_URL`（Chat Completions 的 `/v1` 基地址）、`LLM_MODEL`、`LLM_API_KEY`。运行真实演示再将 `LLM_MODE` 改为 `real` 并重建后端。密钥只给后端，不填写在命令行、聊天、前端构建或证据中。

修改 `.env` 不会更新已经运行的容器；独立 `eval/run.py --smoke` 也不会替网页加载配置。更新模型、地址或密钥后，从仓库根目录执行：

```bash
docker compose --env-file .env -f deploy/compose.yaml up -d --no-build --no-deps --force-recreate --wait --wait-timeout 60 backend
```

然后在 Agent 页点击“开始新任务”再提交。刷新页面会恢复旧 run，旧任务的失败结果仍会显示，不会自动调用新模型。

真实适配器没有隐藏重试和 fixture 回退。此前本机代理的 `deepseek-v4-flash` 通过过真实工具调用往返及 Docker 页面查询验证。当前本机代理的 `gemini-3.8-flash-high` 已通过独立 smoke（6.373s）和 Docker 网页原问题复测（12.305s，状态/历史/故障说明三工具成功）；该配置历史60次按修正后的合同重算自动检查57/60，A19三次超时仍保留；真人复核未完成，且这些历史结果不替代v2最终132次评测。此前 `gpt-5.6-luna` 完整 60 次自动检查 36/60，通过数不足；具体失败和耗时见 [本轮报告](artifacts/acceptance/real-model-luna-20260922T104501Z/report.md)。此前 NVIDIA 配置在最终回答阶段超时，失败证据保留；这不代表任意兼容端点都可用，也不替代完整 60 次效果评测。缺配置会明确报错。独立评测使用相同 create_app、真实 API/工具和每例临时库，在 lifespan 启动后加载固定夹具，只冻结数据时钟。

```bash
ACCEPTANCE_STAMP=$(date -u +%Y%m%dT%H%M%SZ)
# 首次配置端点先验证真实工具往返；不替代60案例评测
uv run python eval/run.py --mode real --smoke --output "artifacts/acceptance/model-smoke-$ACCEPTANCE_STAMP"
uv run python eval/run.py --mode real --repeat 3 --output "artifacts/acceptance/real-$ACCEPTANCE_STAMP"
uv run python eval/run.py --summarize "artifacts/acceptance/real-$ACCEPTANCE_STAMP" --review-file eval/manual-review.json
```

如果模型地址是宿主机的 `127.0.0.1`，容器无法直接使用该回环地址。通常先使用服务商的可访问 API 地址；对于必须保留本机回环监听的模型代理，本项目提供可选的宿主机转发脚本。当前代理使用 8317 端口，Docker 私有网桥监听 18317：

```bash
# 已存在默认 deploy Compose 网络；此进程在宿主机运行，保持终端打开
MODEL_BRIDGE_IP=$(docker network inspect deploy_default --format '{{(index .IPAM.Config 0).Gateway}}')
uv run python scripts/local_model_bridge.py --listen-host "$MODEL_BRIDGE_IP" --listen-port 18317 --target-port 8317
```

本地 `.env` 中保留原 `LLM_BASE_URL` 给宿主机评测使用，另将 `LLM_DOCKER_BASE_URL` 设为 `http://<上面的网桥 IP>:18317/v1`，并设置 `LLM_MODE=real`。随后运行 `docker compose --env-file .env -f deploy/compose.yaml up -d --no-build --no-deps --wait backend` 重新加载配置。桥接不读取密钥、不记录传输内容，只连接固定的本机回环端口；不要使用 0.0.0.0 监听。Ctrl+C 可关闭前台桥接；关闭后真实模型请求会明确失败，设备采集继续运行。

先前后台桥接的 PID/日志位于忽略提交的 `data/local-model-bridge.pid` 和 `data/local-model-bridge.log`。当前本机回环代理配置已启动该桥接。WSL 或主机重启后需重新启动；Compose 网络重建后应重新确认网桥 IP。以后换成可直接访问的服务商 API 时，清空 `LLM_DOCKER_BASE_URL`，让容器使用 `LLM_BASE_URL`。

原A01—A20与新增B01—B24各执行3次，分别60/72例，共132次案例执行；一例可以含多轮模型调用或多个run，包含案例内部的幂等/引用前置步骤。机器检查工具参数、证据与数据库结果；人工逐例检查答案语义和关键错误。运行后输出 review-template.json，复制到 eval/manual-review.json 后逐项填写实际 reviewer、reviewed_at、success 和 critical_errors，保持 evidence_sha256 与原始证据一致。没有真实人工评审时保持 PENDING_REVIEW，不自动填写 reviewer。若提示词、模型、Schema 或工单逻辑改变，应为最终版本重新完整评测。

### v2 评测与性能入口

```bash
# 每次使用新输出路径；这些脚本不会清空开发库
uv run python scripts/acceptance_v2.py --suite iot --output artifacts/acceptance/v2/iot-run-01
uv run python scripts/acceptance_v2.py --suite ai --output artifacts/acceptance/v2/ai-run-01
uv run python scripts/acceptance_v2.py --suite resilience --output artifacts/acceptance/v2/resilience-run-01
uv run python scripts/acceptance_v2.py --suite performance --output artifacts/acceptance/v2/performance-run-01
# 仅重测某一性能模块时使用下列独立入口
uv run python scripts/query_performance_v2.py --output artifacts/acceptance/v2/query-run-01
uv run python scripts/stability_v2.py --output artifacts/acceptance/v2/stability-run-01
uv run python eval/run_v2.py --mode real --repeat 3 --output artifacts/acceptance/v2/model-run-01
uv run python eval/run_v2.py --summarize artifacts/acceptance/v2/model-run-01 --review-file eval/manual-review-v2.json
```

上述v2入口的结果注明自动子断言范围；整体XAC与M阶段仍需汇总完整证据。完整performance入口已包含一次60分钟稳定性，独立stability命令用于单独运行，不把两轮数据混成一个样本。逐例人工复核操作见 [真实模型复核说明](docs/real-model-review.md)。

B09已依据验收通则和实际会话查询定稿为“未声明窗口，合法1—60分钟”，完整600秒/3333Wh断言保持不变。`--case B01,B21,B22 --mode fixture --repeat 1`仅用于入口诊断，不替代72例门槛。稳定性`--minutes 1`也仅为诊断，不算60分钟验收。

脚本退出码：0通过、1已知失败/必需项未运行、2环境阻塞、3待真人复核，优先级2→1→3→0。自动失败与待评审可以同时存在；不得用3掩盖已知失败或自动填写真人结论。

## 说明与边界

- [v2开发方案](docs/AI_IoT_Agent_v2.0_开发方案.md) / [v2验收方案](docs/AI_IoT_Agent_v2.0_验收方案.md)；未调整条款仍回归[v1计划](docs/AI_IoT_Agent_开发计划.md)与[v1合同](docs/AI_IoT_Agent_验收规则.md)
- [架构](docs/architecture.md) / [设计取舍](docs/decisions.md) / [已知限制](docs/known-limitations.md)
- [3—5 分钟演示脚本](docs/demo.md) / [求职表述草案](docs/career-notes.md)

温度阈值和设备数据均为合成演示。未实现实体硬件、模型训练、MCP、向量 RAG、多 Agent 或电路控制。思想参考 EMQX [sdv-mcp-demo](https://github.com/emqx/sdv-mcp-demo)，本仓库的遥测可靠性、工单、前端与测试为另行实现，没有复制该示例代码。第三方依赖遵循各自许可，版本与归属见 [来源声明](docs/third-party-notices.md)；原创仓库尚未授予外部开源许可。
