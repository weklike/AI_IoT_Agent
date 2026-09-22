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
