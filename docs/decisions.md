# 实施决定

## 2026-09-22 / Task 1

- 沿用 v1.1 设计，在现有目录初始化 Git develop；原目录只有文档，不另建平行项目或 worktree。
- Python 3.12.13 由 uv 管理；uv 0.11.3；Node 24.13.0。精确 Python/npm 依赖分别见 uv.lock、frontend/package-lock.json。新依赖均对应合同：pydantic-settings 读取配置；httpx 用于模型 HTTP 与 API 测试；ruff 仅开发检查。
- 项目原创代码暂不授予外部开源许可（未添加 LICENSE）；不复制参考项目代码。第三方依赖保留各自许可；发布前再由所有者确定仓库许可。
- SQLite 时间以固定宽度 UTC ISO 字符串持久化，保证时区往返和时间排序；7 张业务表按计划建立。每个连接应用 FK / busy timeout，初始化验证 WAL。
- Pydantic 数字字段严格且有限；UUID/时间按正常 JSON 字符串解析，时间必须有时区。仅数值严格，避免合法遥测全部被拒。
- MQTT 健康探测使用真实 paho 连接；业务订阅在 Task 3 接入。测试禁用 MQTT 明示 disabled，local 不允许禁用。
- 前端首次解析的 ECharts 5.6.0 被 npm audit 标记 GHSA-fgmj-fm8m-jvvx；在首次建仓阶段将此项改为 6.1.0，审计已无漏洞，未全树升级。
- 镜像固定版本：Python 3.12.13-slim、uv 0.11.3、Node 24.13.0-alpine、Mosquitto 2.0.22、nginx 1.28.0-alpine。当前 Compose 是 Task 1 的三服务骨架，Task 2 增加真实模拟器；不能视为 AC-01。
- 原两份文档引用的修订说明缺失，保留原文引用并记录，不补造其内容。

## Task 5—7

- 工单写入使用 SQLite BEGIN IMMEDIATE 获取写入保留锁后查询证据，数据库部分唯一索引兜底；网络/模型等待不占事务。当前 tool_call 的成功结果与工单同事务提交。
- AgentRun 在七表范围内增加 messages_json、model_metrics_json，保存完整 assistant/tool 协议与模型耗时/token 可用性。无新增模型日志表。
- 真实适配器使用 Chat Completions 函数工具协议，经 [官方函数调用文档](https://developers.openai.com/api/docs/guides/function-calling) 核对 assistant 在前、tool_call_id 配对规则。当前只有模拟 HTTP 协议测试，尚无经过真实调用验证的 endpoint/model。
- fixture 是明确标记的确定性演示脚本，只替换模型响应；其数值与工单号来自真实工具。real 失败不切换模式。
- 字体优先本地中文字体和等宽数字；深色导航、浅色面板、文字状态。无额外 UI 框架、外部字体或图像依赖。

## 稳定性审查修正

- 固定 DataClock 会让多个工具 started_at 相同，因此增加 ToolCall.ordinal 保存执行顺序；不使用随机 UUID 的字典序代替时间顺序。
- 模型响应持久化也消耗业务总预算；保存后再次检查 deadline，不能在已过期时返回 completed。
- 模型失败/超时同样记录耗时；正常最终响应允许空 tool_calls 列表，但空正文仍为协议错误。
- 未授权或非法工具在执行前拒绝，同时保存服务器失败轨迹；不会进入业务服务。
- 场景超时更新若遇 SQLite busy，记录具名任务错误，不留下未检索异常。后续显式命令查询可持久化已经过期的状态，不通过隐藏循环重试写入。
- 场景 POST 尚未返回时离开详情页，取消请求并阻止后续响应重启旧轮询。
- 测试镜像以源码摘要命名并复用只读构建产物，每次容器/卷/端口/前缀仍独立；避免重复测试因不必要的镜像元数据网络请求被阻塞。

## Task 8 性能与证据沿用

- 60 分钟稳态窗口保存 5391 个 PUBACK ID，全部在 DB 中匹配；遥测提交 P95=79.497ms。原 API 1000 请求 P95=650.164ms，保留 FAIL，不覆盖。
- 5403 条三设备整小时预置数据复现 P95=624.129ms。profile 显示递归 JSON 编码与逐条 ORM 实例化为可消除开销。使用已有 Pydantic 序列化及仅查询历史所需字段的 NamedTuple，最新同规格 P95=404.300ms，零错误；不缩短窗口、不截断统计、不放宽阈值。
- `performance-final/report.json` 分别引用原稳态和新 API 样本；`performance-compatibility.json` 对比实际运行镜像源文件摘要。沿用范围限于未改变的 MQTT/模拟器/入库链路、总览可见与稳定性；新的历史查询和图表由定向测试、压测及 E2E 重新验证。
- 历史 API 的 gap_before 表示相邻真实样本间隔超过 1.5 个配置采样周期（容忍半周期抖动）；前端断开曲线，仅用 null 标记绘图空窗，不插入业务样本、不影响统计。
- Docker 将锁定依赖安装层放在源码 COPY 之前，并使用 uv 构建缓存。PyPI 超时的两次构建均保留日志。测试环境可显式指定 CHARGE_TEST_DEPENDENCY_IMAGE，只有 uv.lock 与 pyproject.toml 字节完全相同时才复用其依赖，然后复制当前源码并离线 uv sync；测试卷和实例仍全新。此选项不更改正式 Compose 的镜像来源。
- 最终证据审计发现旧 hold.mjs 的 Playwright 默认信号处理先关闭浏览器，导致 SIGTERM 收尾截图失败。60 分钟期间的完整采样/观察 JSON 已保存，但旧 browser-final.png 不存在；该失败日志保留。关闭 Playwright 自带的 SIGTERM/SIGINT 处理，由脚本先保存截图再关闭，验收入口检查浏览器退出码。新 cold-start-capture 已实际保存截图并正常退出；不补造旧窗口的结束截图。
