# OpenTelemetry 与 Langfuse 分步验收记录

日期：2026-10-11。范围：本次新增的可选追踪、Collector 转发、Agent 与动作链路关联、合成 E2 实验及评分。此记录不代表 E5 企业试运行放行。

| 步骤 | 验收证据 | 结果 |
|---|---|---|
| 1. 依赖与容器 | `uv sync --frozen --extra dev --extra observability`；`docker compose -f deploy/gateway/compose.yaml build agent web` | Python Agent 与 Next.js Web 镜像均构建通过 |
| 2. Web → Agent 追踪 | Next.js 生产服务代理请求到测试上游；上游收到有效 W3C `traceparent`，没有收到 `baggage`；FastAPI 远程父 span 提取测试通过 | 通过 |
| 3. Agent 与数据边界 | 使用本地 `FunctionModel` 的真实 HTTP/SSE 请求向 debug Collector 输出 13 个 spans；运行记录的 trace/span ID 与 `operion.agent.run` 一致；超时流有终态，提示内容未进入 spans | 通过 |
| 4. 审批与 Worker | 24 项独立 PostgreSQL 测试通过，含 Worker 根 span 链接到持久化审批 span；原动作账本的 UNKNOWN、幂等与恢复测试通过 | 通过 |
| 5. Langfuse Collector | 固定版本 Collector 配置校验通过；测试 span 被转发到模拟 Langfuse `/api/public/otel/v1/traces`，Basic Auth 与 ingestion version `4` 正确 | 通过 |
| 6. Langfuse 合成实验 | 真实本地模型执行 1 个合成 E2 用例；实验 trace/span ID 与模拟 Scores API 的 `traceId`/`observationId` 一致，`BOOLEAN` 分数使用数字 `1` | 通过 |
| 7. 总回归 | Python 196 项（其中 24 项因数据库隔离在离线组跳过）；PostgreSQL 24/24；Web TypeScript 与生产构建；`git diff --check`、Ruff | 通过 |
| 8. 实模评估 | E2 15 例 × 3 次，45/45 通过；报告位于 `reports/enterprise/observability/20261011/e2-final.json` | 通过 |
| 9. 真实 Langfuse 接收 | 启动 `collector-langfuse.yaml`；无内容的父子测试 Span 经 Collector 导出后，在 Observations API v2 按 Trace ID 查回两条，父子关系正确；Collector Auth 与项目密钥一致 | 通过 |
| 10. 真实 Langfuse E2 | 合成 C01 单次实模评估 1/1 通过；Trace `e34a130fd67ff0be87c94904c53ac679` 查回 8 个观察节点，含 EVALUATOR、AGENT、TOOL 和两次 GENERATION；Scores API v3 返回绑定到根观察节点的 `operion_correctness=true`；实验 ID `316017efe18d4285859b1a168b3c4d90` 可查询 | 通过 |
| 11. 真实 Langfuse UI | [Trace 页面](https://cloud.langfuse.com/project/cmv41jt6h05egad0el9rcy2kh/traces/e34a130fd67ff0be87c94904c53ac679)显示完整树、模型 token 数和根节点评分；[实验结果页](https://cloud.langfuse.com/project/cmv41jt6h05egad0el9rcy2kh/experiments/results?baseline=316017efe18d4285859b1a168b3c4d90)显示 1 个项目、`operion_correctness` 为 100% true | 通过 |

实模验收首轮暴露评分器误报和“上游不可用”测试仓库接口缺失；修复并增加反例后，最终版本重新执行 45/45 通过。原始答案与工具证据保存在本地报告中，报告目录按仓库规则不纳入 Git。

**真实项目验收：** 已配置 Langfuse Cloud 项目地址和密钥，真实 OTLP 接收、查询 API 和 UI 均通过。合成单例报告保存在本地 `reports/enterprise/observability/20261011/e2-langfuse-live.json`，该目录按仓库规则不纳入 Git。Collector、Web 和 Agent 容器正在运行，Web 与 Agent 已以 `OPERION_OTEL_ENABLED=1` 重建并通过健康检查。Web 的每 3 秒健康检查也会产生 `GET`、`middleware GET`、`start response` 观察节点；长期运行前应控制这部分上报量。本次未从认证后的 Operion 浏览器发起实际 Web → Agent 业务请求；该跨服务链路已有本地传播测试，真实 Langfuse UI 中的跨服务业务追踪仍需单独点验。认证网关的实际浏览器点击和 E5 长期观察属于原路线图的其他验收范围。

**依赖审计：** `npm audit --omit=dev` 报告 3 项既有生产依赖告警（Next.js critical，Sharp 与 source-map-js high）；原始锁文件已固定 Next.js 16.3.5。本次追踪接入未调整这些基础依赖，镜像构建与功能测试通过，但这些告警需要单独升级与回归，不能计为安全审计通过。
