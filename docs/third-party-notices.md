# 来源与第三方依赖

核对日期：2026-09-23。以下版本与许可来自本仓库锁文件安装后的包元数据；不替代各发行包完整的 LICENSE、NOTICE 或传递依赖声明。

业务实现、合成设备协议、验收夹具和24篇模拟系统知识资料由本项目编写。资料不是厂商维修手册，温度、电量和控制阈值只用于软件演示。知识文件逐篇记录 source_kind、license_note、版本及适用型号，引用保留实际段落摘要。

项目思想参考 EMQX 的 sdv-mcp-demo，仓库地址已列在 README。当前实现没有复制该示例代码；设备链路是 MQTT，Agent 工具在后端进程内调用，不宣称实现 MCP over MQTT。

| 直接依赖 | 当前安装版本 | 包元数据许可 |
|---|---|---|
| FastAPI | 0.141.1 | MIT |
| Pydantic | 2.13.5 | MIT |
| SQLAlchemy | 2.0.54 | MIT |
| aiosqlite | 0.22.1 | MIT（核对发行包内 LICENSE） |
| paho-mqtt | 2.1.0 | EPL-2.0 OR BSD-3-Clause |
| HTTPX | 0.28.1 | BSD-3-Clause |
| Uvicorn | 0.53.0 | BSD-3-Clause |
| Vue | 3.5.43 | MIT |
| Vue Router | 4.6.4 | MIT |
| ECharts | 6.1.0 | Apache-2.0 |
| Vite | 6.4.3 | MIT |
| TypeScript | 5.7.3 | Apache-2.0 |
| Playwright Test | 1.58.2 | Apache-2.0 |
| pytest | 9.1.1 | MIT |

完整 Python 依赖版本见 `uv.lock`，前端版本见 `frontend/package-lock.json`。Compose使用的Mosquitto、Nginx、Python及Node基础镜像分别遵循镜像内各组件许可；发布二进制或镜像时应随发行物保留对应声明。本仓库当前没有向外部授予原创代码的开源许可。

真实模型服务为用户自行配置的端点；不在仓库或测试产物分发账号、认证头和密钥。模型输出及第三方服务条款不因本项目依赖的开源许可而改变。
