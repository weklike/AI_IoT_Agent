# 充电设备监控与运维 Agent

开发基线见 [开发计划](docs/AI_IoT_Agent_开发计划.md) 和 [验收规则](docs/AI_IoT_Agent_验收规则.md)。实际完成度见 [进度](docs/PROGRESS.md)。当前为开发中的 Task 1 骨架，业务功能及 G1/G2/G3 未验收。

要求 Linux/WSL2、本地磁盘、Docker Compose、uv、Node ≥22.12。项目使用 Python 3.12（uv 自动准备）。

```bash
# 仅首次创建；已有 .env 不覆盖
[ -e .env ] || cp .env.example .env
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend exec -- playwright install chromium
# 浏览器缺少系统库时，由管理员安装：
# npm --prefix frontend exec -- playwright install-deps chromium

docker compose --env-file .env -f deploy/compose.yaml up -d --build
# http://127.0.0.1:8080

uv run pytest tests/unit tests/integration -q --junitxml=artifacts/acceptance/backend.xml
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

本机调试后端：`uv run uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1`。需要实际 Broker；未连接时 `/api/health` 返回 503。前端调试：`npm --prefix frontend run dev`。本机数据库在 data/，容器使用独立卷；不要让两者写同一数据库。模型配置只给后端；fixture 不需要密钥，real 缺配置会明确报错。

测试自行创建临时 SQLite / 独立 Compose Broker、随机端口与 MQTT 前缀，仅清理自有资源。当前无数据重置入口；不要删除开发数据来运行测试。尚未实现的验收和评测入口不能用于宣称通过。

三台设备及温度阈值均用于合成演示，不代表真实充电设备认证。MQTT 是设备协议，Agent 计划使用进程内函数工具；未实现 MCP、向量 RAG 或模型训练。上游思想参考及边界见开发计划第 11 节，自写实现与选择见 [decisions](docs/decisions.md)。
