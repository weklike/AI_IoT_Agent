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
