# v2.0 顺序实施计划

执行方式：使用 executing-plans 与 test-driven-development，在当前 develop 工作区顺序推进，不开启并行代理。用户已批准的完整业务设计、文件清单、命令及任务依赖以两份 v2.0 正式方案为准；本文件细化当前迁移任务。

目标：实现 F01—F07 并依 v2.0 验收方案验证 M4；人工评审留给真实人员。
架构：保留单体和现有服务；编号 SQL 迁移作为唯一建表路径；业务操作幂等与结果在调用方事务内提交。
技术：现有 Python/SQLAlchemy/SQLite、Vue/TypeScript，无新增框架。

- [ ] T00：同步授权和旧约束历史；确认演示资源所有权；运行既有 unit/integration 全量基线，记录日志与 JUnit。
- [ ] T01.1：在 tests/integration/test_migrations.py 建立真实 v1 schema/业务行，先测试迁移版本缺失失败；保存固定 v1 SQL 夹具，不依赖可变 ORM 建旧库。
- [ ] T01.2：backend/app/migrations/ 编号 SQL、SHA256 和事务应用；显式 BEGIN EXCLUSIVE，拒绝缺号、摘要篡改、未知版本和未知旧 schema；错误回滚全部 DDL。
- [ ] T01.3：新增 v2 schema 与 ORM 映射；空库和存量库同迁移路径；tests 对比表列、类型、空值、索引与 FK，并核对旧行摘要。
- [ ] T01.4：scripts/migrate.py 实现只读 check、SQLite backup 一致备份、apply、新路径 restore；备份清单记录摘要版本；测试 WAL 内容、拒绝覆盖与失败回滚。
- [ ] T01.5：operations.py 实现路由/动作/参数摘要与 request_id 查询、冲突及结果写入；事务回滚和并发独立会话测试；原 Agent 幂等不改动。
- [ ] T01.6：运行 migration/operations 定向测试及既有受影响回归；记录 XAC-01—04 已覆盖子断言。XAC-04 全部新 API 要到相应任务完成才可 PASS。
- [ ] T02—T11：逐项执行正式开发方案 §13 对应清单、命令及验收映射；每项先风险失败测试，再实现、验证、更新 PROGRESS。完整真实模型评测与一小时负载集中在最终版本，保持全部失败证据。

T01 首条验证：`uv run pytest tests/integration/test_migrations.py tests/integration/test_operations.py -q`。
