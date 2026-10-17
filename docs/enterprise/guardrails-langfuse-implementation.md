# Guardrails 与 Langfuse：实施及验收

> 当前实现已改为 [结构化回答与证据契约](structured-answer-evidence.md)，下文的文本解析策略及旧验收结果仅作历史记录。

> 后续更新：相关显式事实、测试隔离及依赖问题已于 2026-10-17 修复；见 [实施和验证记录](fixes-2026-10-17.md)。下文保留当时证据与限制。

日期：2026-10-11。范围：Agent 只读回答的运行时事实校验，以及现有安全门禁的回归证据。原有身份、对象权限、Action Store/Worker 与审批状态机仍是执行门禁。本工作不扩大写权限，也不把 Langfuse 当作放行条件。

## 实施顺序与阶段门槛

| 阶段 | 交付 | 阶段验收 |
|---|---|---|
| 1. 基线 | 盘点现有认证、工具过滤、对象权限、快照/live、写入门禁和离线评测 | `scripts/verify.sh offline`；记录已覆盖与待补的范围 |
| 2. 发送前事实校验 | 离线与运行时共享声明提取；Agent 暂存模型文本，完成后核对服务端工具证据 | 错误订单数、金额、对象、状态、履约结论不能进入 SSE 或成功历史；正确结果仍能显示 |
| 3. 观察与对抗测试 | 对输出门禁记录无业务内容的 OTel `guardrail` 子 span；复用并补充真实执行路径测试 | Span 与 Agent run 同一 trace；理由码不含问题或业务记录；本地断言决定通过/失败 |
| 4. 真实场景 | 使用已导入的 WWI 公开来源样本、运行中的 SGLang 与真实 FastAPI/AG-UI 路径；按可用凭据追加在线 ERPNext/Twenty GET-only 验证 | 独立统计预期与工具结果一致，回答和运行记录一致，Langfuse 中实际可查到 Guardrail 节点；清楚标识 snapshot/live |
| 5. 总验收 | 离线、隔离 PostgreSQL、Web 构建、真实模型场景、追踪 UI 与隐私检查 | 保存命令、版本、数据模式、预期、实际和未验收项 |

## 执行设计

- 对明确声明的订单数、金额、canonical ID、订单状态和履约结果，使用服务端记录的成功工具结果核对。无证据或矛盾时阻止回答发送。安全的不确定表述可以继续显示。
- AG-UI 的工具事件可继续发送；文本消息事件暂存到模型完成之后。失败时发送通用 `OUTPUT_UNVERIFIED` 错误，运行记为失败，不保存该答案为成功历史。这个策略改变文本首字延迟，但保留协议和工具进度。
- `ALLOW`、`DENY`、`UNKNOWN` 是输出校验结论，不替换认证 HTTP 状态、来源故障结果或 Action Worker 的 `UNKNOWN` 副作用状态。观测 span 只含门禁名、结论、稳定理由码和策略版本。
- 现有 `unittest` 与 CI 是发布门槛；Langfuse 仅接收观察结果。继续使用现有 OTel → Collector → Langfuse 路线与 Scores API，不增加第二套 trace exporter。

## 边界

规则只覆盖能确定解析的**显式**声明；自然语言中的隐含推断、实体与多个数值之间的复杂指代，还需要业务事实卡片和更强的结构化输出。分页 `partial` 不意味着过滤后的 `total_count` 不可用，但 `full_source_history=undetermined` 禁止把它称作全部历史。在线模式也只代表当前授权且已导入的数据集，不能推断源系统全历史。输出门禁不替代业务写入的审批和 Worker 检查。

## 分步验收结果（2026-10-11）

| 阶段 | 实际执行与证据 | 结果 |
|---|---|---|
| 基线及回归 | `scripts/verify.sh offline`：共 204 项，其中 180 项通过、24 项隔离 PostgreSQL 用例在离线组跳过；隔离 `postgres:16` 中 24/24 通过 | 通过 |
| 输出发送门禁 | `tests/test_output_guardrails.py` 与 `tests/test_agent_app.py`：错误计数、金额、对象、状态、履约和来源故障被拦截；错误文本未进入 SSE 或成功会话历史 | 通过 |
| Web | `scripts/verify.sh web`：TypeScript 和 Next.js 生产构建通过；本地浏览器分别完成 snapshot 和 live 页面交互 | 通过 |
| 真实模型快照 | SGLang `qwen3.8-27b`、WWI `interview-wwi-v1` 公开来源快照：客户 65 为 10 单、订单 66823 净额 USD 177.60、写权限拒绝及注入错误计数，共 4/4 | 通过；结果见 `reports/enterprise/guardrails/20261011/acceptance-snapshot-final.json` |
| 真实在线业务源 | 使用 `.env` 中的 `TWENTY_API_KEY_READ_ONLY` 与 `ERPNEXT_API_KEY_READ_ONLY`，直接 GET 两个系统，并以 `wwi-v1-small-20260919-e1` 已导入公开 WWI 样本独立核对：客户 11 为 1 单、订单 73595 在线净额 EUR 2160.0、当前 ERPNext 状态 Draft；再经真实 Agent/模型运行 4/4 | 通过；结果见 `reports/enterprise/guardrails/20261011/acceptance-live-final.json` |
| 浏览器真 UI | 本地 Web → FastAPI Agent → 两个在线系统 → SGLang；页面显示客户 11 的 1 单、`live · public_sample` 证据卡与订单 73595 的 EUR 2160.0/Draft | 通过；本地只读测试入口 `http://127.0.0.1:3002/` |
| Langfuse | 8 个最终场景 Trace 均含与 `operion.agent.run` 相连的 `GUARDRAIL` 子节点；错误计数场景为 `deny / ORDER_COUNT_MISMATCH`，Guardrail 节点 Input/Output 均为空；真实在线场景发布 `operion_guardrail_acceptance` Boolean Scores | 通过；[在线拒绝 Trace](https://cloud.langfuse.com/project/cmv41jt6h05egad0el9rcy2kh/traces/2e60253665108c44205f90c886ede3ad) |

最终代码已重新构建并替换本地 Gateway 的 Agent/Web 镜像，两个容器健康检查均为 `healthy`；网关配置仍以 `interview-wwi-v1` 的 snapshot 模式运行，在线验收使用隔离的本地只读 Agent。Langfuse 8/8 逐条 API 核验记录保存在 `reports/enterprise/guardrails/20261011/langfuse-final.json`，最终在线拒绝 Trace 的 UI 同时显示 `operion_guardrail_acceptance: True`、`GUARDRAIL` 节点、`deny` 和 `ORDER_COUNT_MISMATCH`。

在线验收的预期金额和状态来自 ERPNext 只读 API，客户身份另由 Twenty 只读 API 验证。原始 WWI 行的状态是 `open`，当前 ERPNext 订单为 `Draft`；回答和校验采用当前在线值，没有把来源快照状态误称为实时状态。`reports/` 按仓库规则忽略，保存了每个场景的回答、事件类型、工具名、运行状态和 Trace ID。线上数据库还含其他导入/模拟数据，因此本结论只覆盖被选定的授权 WWI 样本；`full_source_history` 仍是 `undetermined`。

首轮实模验收发现 Markdown 加粗的 `**1** sales order` 未被共享计数解析器识别；修复并增加反例后，最终在线 4/4 通过。离线快照首轮也暴露金额格式和“没有删除订单”否定句解析问题，修复后重跑。测试评分中预期的 `DENY` 计为测试通过；Langfuse 的 Scores 只是本地判定副本，不参与运行时放行。

## 重跑命令

```bash
scripts/verify.sh offline
scripts/verify.sh web
OPERION_OTEL_ENABLED=1 OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces PYTHONPATH=src .venv/bin/python scripts/accept_guardrails.py --output reports/enterprise/guardrails/snapshot.json --publish-langfuse-scores
OPERION_OTEL_ENABLED=1 OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces PYTHONPATH=src .venv/bin/python scripts/accept_guardrails_live.py --output reports/enterprise/guardrails/live.json --publish-langfuse-scores
```

命令要求本地 SGLang、OTel Collector 和两个业务系统正在运行；评分选项还要求 `.env.langfuse.local` 的 Langfuse 项目密钥。在线脚本只读取 `.env` 中明确命名的只读 API key，从未加载管理 key，也不调用写接口。当前 HTTPS 认证网关在内置浏览器中因本地 CA 未受信任而无法完成浏览器点击验收；这里的真实 UI 验收使用 `localhost` 本地只读入口，不能替代 OIDC 网关或 E5 长期试运行验收。Web 依赖审计仍报告 3 项既有告警（2 high、1 critical），本次的功能验收不等于依赖安全审计通过。
