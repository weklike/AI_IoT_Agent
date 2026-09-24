# 开发进度

- 业务基线：用户授权的v2.0开发与验收方案，未调整条款继续回归v1.1。
- 当前任务：V2-T11仍待真实人员复核；当前准备仓库内容的PR。
- 分支：pr/v2-current-content；业务冻结提交603d152；PR准备基线6271aad，未推送。
- 更新时间：2026-09-24T15:13:32+08:00
- 历史失败及修正：[前一检查点](progress-history/20260923-before-final05.md)、[历史](progress-history/20260923-v2-t11-checkpoints.md)、[设计记录](decisions.md)。

## 任务状态

任务DONE不等于对应XAC或M阶段PASS。v1.1九项任务的历史状态保留在快照，本表为当前v2.0任务。

| 任务 | 状态 | 证据或剩余事项 |
|---|---|---|
| V2-T00 方案与基线 | DONE | 用户明确授权，合同与案例口径记录齐全 |
| V2-T01 迁移与操作幂等 | DONE | b7208cf；旧库摘要、WAL备份、空库schema及重复请求 |
| V2-T02 模拟器与报告 | DONE | 1b9194f；双协议、整数计量、报告重发、状态卷 |
| V2-T03 控制与会话接口 | DONE | 1b9194f；回执/效果独立、超时/重启与实际Broker |
| V2-T04 功率计划 | DONE | daef400；预览、先降后升、保守上界、30+5秒 |
| V2-T05 告警 | DONE | 8d01288；连续观测、恢复、确认及版本边界 |
| V2-T06 工单生命周期 | DONE | 8d01288；未关闭幂等、恢复证据、原子事件与请求 |
| V2-T07 知识检索 | DONE | a37ac94；24篇、版本化FTS5、32条冻结检索验证 |
| V2-T08 Agent与巡检 | DONE | bfe05dd；九工具、单槽位、同run引用、只读巡检 |
| V2-T09 时间线与脚本 | DONE | 5e28303；真实来源、只读复盘、固定60秒场景脚本 |
| V2-T10 三页面集成 | DONE | 652aaf8；完整30项E2E、双分辨率；新增知识安全3项 |
| V2-T11 综合验收与交付 | IN_PROGRESS | 最终自动验收已完成；132例真人语义及文档/演示复核待完成，M4保持PENDING_REVIEW |

## 本次变更

- 最终提示词明确资料检索与实际设备/会话查询职责，减少重复检索；预算、案例和评分阈值未放宽。
- 未确认控制回执改用警示外观，只有实际反馈verified才显示成功；已先复现再修复。
- 汇总AC-01—40与XAC-01—60的实际证据、源码摘要和环境，保留所有旧失败，不拼接不同模型轮次。
- 生成132例实际回答、原始证据链接及未填写的真人评审模板。

## 实际验证

下列短路径位于artifacts/acceptance/v2/；重叠测试不累加。

| 命令/实际验证 | 退出码 | 结果 | 证据 |
|---|---:|---|---|
| `uv run pytest tests/unit tests/integration -q --junitxml=artifacts/acceptance/v2/backend-candidate05-final.xml` | 0 | PASS，388项，682.16秒 | backend-candidate05-final.xml/log |
| 最终原A60、新增B72完整真实评测 | 各3 | PENDING_REVIEW；自动60/60、72/72，各类别12/12，自动关键错误0 | real-baseline-20260923-final-05/、real-v2-20260923-final-05/ |
| typecheck/build、完整E2E及定向复测 | 各0 | PASS；完整30项、知识3项、最终控制2项、布局2项 | frontend-verification-candidate05.json；E2E原件见验收核对 |
| 原/新增API及知识压测 | 各0 | PASS；P95 414.495/443.664/23.601ms，零错误 | query-baseline-20260923-final/、query-v2-20260923-final/ |
| 控制/告警20次可见性、20次功率保护 | 各0 | PASS；两类20/20≤4秒，20次功率计划通过 | visibility-20260923-status-style-final/、power-protection-20260923-formal/ |
| 完整RSS小时及原始窗口相容性重核 | 0 | PASS；5273/5273，入库P95 67.267ms | stability-rss-20260923-formal/、stability-rss-20260923-final05-revalidated/ |
| 独立完整Git克隆，锁定离线安装/构建/76项定向测试 | 各0 | PASS | clean-reproduction-20260923-candidate05/report.json |
| 最终证据/源码/链接/配置边界核对 | 0 | PASS；100项唯一、摘要有效、无当前密钥值泄漏、无自有测试容器遗留 | audit-20260923-final05/validation.json；security-boundary-20260923-candidate05/report.json |
| 四服务旧库升级及空卷启动 | 0 | PASS；原检查错误及更正均保留 | 最终JUnit；cold-start-20260923-final/automatic-recheck.json |

## 未完成与阻塞

- 132条真实模型回答尚无真人语义/关键错误结论，不能代填reviewer或以自动通过数宣称准确率。文档、本人讲解与演示仍需人工复核。
- 最终100项中92项PASS、8项PENDING_REVIEW；M1/M2通过，M3/M4待人工复核；T11尚不能DONE。完整状态见[最终索引](../artifacts/acceptance/v2/audit-20260923-final05/results.json)。
- 小时资源实测属于b000dee实例；最终提示及详情页样式的相容范围单独记录，不声称其资源字节值完全相同。第一次缺少RSS的小时记录保留。
- 旧轮次失败、检索语义局限及ECharts构建体积警告保留；用户既有改动与运行中的deploy实例未触碰。

## 下一步

真实人员从[132例复核入口](../artifacts/acceptance/v2/review-candidate05/INDEX.md)核对工具数据与回答，填写真实身份、时间和结论，再按[复核说明](real-model-review.md)执行summarize；完成文档与演示核对后更新最终验收状态。汇总不重新调用模型；若改业务/提示/Schema则需新一轮完整评测。

## 最新成果展示（2026-09-23）

- 新增v2.0功能导览，明确设备/功率/巡检/Agent入口；独立展示实例 http://127.0.0.1:44468 已运行，原8080实例未触碰。
- 前端typecheck/build退出0；定向E2E 7项通过52.3秒，1280×720和1920×1080无横向溢出；实际完成三台充电、45kW计划、过温建单和巡检。
- 采用fixture明确演示工程流程，保留活动会话与过温场景供查看；不是新增真实模型成绩。旧132例待人工状态不变，受影响源码仅3个前端文件。
- [成果入口、截图与停止命令](showcase.md)，原始失败、修正及PASS证据位于artifacts/showcase/20260923/。

## 审查复核与修正（2026-09-23）

- 十条审查意见逐条复核，结论与取舍见[decisions](decisions.md)末节：构建脚本三项、results.json说明、样式覆盖、更新时间、E2E范围成立并修正；G3事后放宽不成立（用户已于09-22裁决）；启动证据部分成立，改为双链接；直接打开锚点在Chromium不能复现，仅加回归测试。
- 展示构建脚本自行执行typecheck/build、COPY前清除旧文件、不再占用`test-{digest}`标签；复跑PASS见artifacts/showcase/20260923/build-20260923T125048Z/。运行中的44468展示实例未重启。
- 顶层results.json同步当前gemini结论并与此前未入库的证据目录一并提交；v2最终索引不受影响。

| 命令 | 退出码 | 结果 | 证据 |
|---|---:|---|---|
| `uv run python artifacts/showcase/20260923/build-local.py` | 0 | PASS；typecheck/build/两镜像构建均0 | artifacts/showcase/20260923/build-20260923T125048Z/local-build.json |
| `npm --prefix frontend run test:e2e -- --operations --grep anchor`（修改页面前） | 0 | PASS；锚点问题未复现，含反向对照 | artifacts/acceptance/e2e/20260923T124954Z/ |
| `npm --prefix frontend run test:e2e`（四组完整） | 0 | PASS；normal 15、empty 1、failures 3、operations 15，共34项 | artifacts/acceptance/e2e/20260923T125123Z/ |

## PR准备（2026-09-24）

- 从`develop@6271aad`创建`pr/v2-current-content`，仅整理本轮PR验证证据和进度；未改业务代码、模型配置、验收门槛或历史失败。
- 本轮E2E证据位于`artifacts/acceptance/e2e/20260924T070749Z/`；四份JUnit纳入本轮提交，原始Compose日志与截图在本地保留。原有未跟踪的Task 2 MQTT样本与planning记录原样保留，不纳入本轮提交；后端测试另生成一份MQTT样本，同样不纳入。
- 仓库尚无Git remote或远端基分支，且当前环境无`gh`命令和GitHub令牌；推送与线上PR等待目标仓库地址、基分支及可用认证。PR尚未创建。

| 命令 | 退出码 | 结果 | 证据 |
|---|---:|---|---|
| `uv run pytest tests/unit tests/integration -q --junitxml=/tmp/ai-iot-pr-backend.xml` | 0 | PASS；388项，688.11秒 | `/tmp/ai-iot-pr-backend.xml` |
| `uv run ruff check backend simulator tests scripts eval` | 0 | PASS | 本轮终端输出 |
| `npm --prefix frontend run typecheck` | 0 | PASS | 本轮终端输出 |
| `npm --prefix frontend run build` | 0 | PASS；保留原有大包体提示 | 本轮终端输出 |
| `npm --prefix frontend run test:e2e` | 0 | PASS；四组34项，隔离Compose资源已清理 | `artifacts/acceptance/e2e/20260924T070749Z/` |
| `git diff --check` | 0 | PASS | 本轮终端输出 |

下一步：取得目标remote与基分支，获取远端状态并核对实际PR差异；确认认证后只推送本分支并创建PR。M4/G3仍保持PENDING_REVIEW。
