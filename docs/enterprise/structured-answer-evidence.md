# 结构化回答与证据契约

2026-10-17：运行时政策 `structured-evidence-v1` 替代 `business-facts-v2`。删除 `answer_claims.py` 和 `business_facts.py`，不再从自然语言或 Markdown 中反推业务事实。

## 数据流

1. 服务器认证、授权并执行原有业务工具。工具仍负责数据读取与对象权限。
2. `EvidenceRegistry` 对已知工具及版本化结果进行归一化，生成只属于本次运行与权限范围的随机引用。事实包含实体、字段、值、币种、覆盖范围、JSON 指针及来源上下文；表格包含服务器确定的行列。
3. 工具返回 `answer_evidence` 清单。模型通过 `present_answer` 提交严格的 `AnswerPlan`，只能选择当前事实 ID、表格 ID 和允许的列，不能提交业务文字、自定义标题、数值、币种、行数据或“全部历史”声明。
4. 校验引用、上下文、字段、重复选择及证据冲突。无效选择允许一次模型修正；仍失败则不给出业务答案。普通文字没有默认放行路径。
5. 服务器按固定语义标签和证据生成中英文回答。发送 SSE 前再次校验；模型中间文字、输出工具参数及未经验证的部分回答均不发布。只有服务器生成的最终文字进入成功会话历史。
6. 最终 `ModelResponse.metadata["operion.answer_evidence"]` 保存所选事实与表格证据，便于审计及验收；浏览器公开历史接口仍只返回既有消息结构。原有历史不重写，取消或失败的运行不保存新答案。

## 校验边界

| 场景 | 约束 |
| --- | --- |
| 客户人口与有单客户 | `customer_count`、`customers_with_orders` 独立；完整订单列表只能推导有单客户数，不能证明客户人口总数 |
| 分页与总数 | `page_order_count` 来自返回行；筛选总数只来自明确的 `completeness.total_count` 或组织汇总；分页客户分布不能提升为完整分布 |
| 实体与金额 | 表格不能修改或重排值；投影强制保留身份列，金额强制保留币种，数量保留单位。缺币种的金额显示未知，其他证据可用；非法金额不生成有效证据 |
| 状态 | 来源状态、业务状态、单据状态及拣货/交付字段各自保留字段语义，不相互替代 |
| 缺失与零 | `None`/未暴露字段/来源故障均不能生成零事实；显式零仍可显示；联系字段保留 present/explicit_empty/not_exposed |
| 时效与覆盖 | 绑定运行、租户/用户/授权范围、工具、查询条件、来源模式、业务日期、观测时间、完整性及来源警告；快照场景履约结论不能冒充 live 结果 |
| 冲突与越权 | 同一运行中相同对象字段的矛盾证据不能任择其一；发现关系对象越出范围时整次归一化回滚 |
| 操作能力 | 能力查询不证明已执行；提案仅接受 `PENDING_APPROVAL`，固定说明尚未执行。原有审批与 Worker 门禁保持独立 |
| 来源文本 | 名称等来源字符串以数据渲染并转义 Markdown/HTML，不作为模型指令、列标签或任意回答文字 |

这里验证的是**所选择事实的证据支持性**。模型仍可能选错工具、漏选事实或没有完成问题，所以 E2 还需独立检查工具选择、参数、预期事实是否真正出现在回答中，不能把结构化合法等同于任务完成。工具和业务源本身仍是事实的可信边界；未知工具或契约版本无法生成有效事实。复杂推导、税额/币种换算等必须先增加有类型、带来源的领域计算工具，再通过新契约暴露，不能重新添加自由业务 prose 通道。

## 回归与观测

- `test_business_fact_binding.py`：两次生产误拦截复现（总数 30/单页 1；30 单/8 个有单客户）、中英文、实体/字段/币种/范围不可覆盖、旧运行/跨范围引用、冲突证据、销售与采购区分。
- `test_output_guardrails.py`：零/缺失/故障、未知契约、字段投影、履约、提案与能力、源文本注入、空/重复/伪造引用。
- `test_answer_evidence_contracts.py`：用实际仓库输出覆盖读工具适配器，避免只用手写形状自证。
- `test_agent_app.py`：无效输出不进入 SSE/成功历史，最终文字与恢复历史一致，权限变化保留可见对话并刷新模型上下文，取消路径不发布部分答案。
- `test_e2_evaluation.py` 与两份 `accept_guardrails*.py`：按所选结构化证据评分，真实模型验收的预期仍分别来自 CSV 或独立只读业务 API。

Langfuse 的 `operion.guardrail.output_facts` 记录稳定原因码、策略版本、事实/表格数量与已知引用；未知引用的原始模型字符串不写入内容关闭的诊断。工具契约错误另记 `operion.guardrail.evidence_contract`。最终运行 span 记录验证过的引用计划，业务正文仍遵循现有内容捕获开关。校验不依赖 Langfuse 是否可用。

重跑：`scripts/verify.sh offline`；定向：`scripts/verify.sh case fact-binding`；实模：`PYTHONPATH=src .venv/bin/python scripts/accept_guardrails.py --output /tmp/operion-guardrails.json`。数据库测试使用既有隔离 PostgreSQL 工作流；本次不更改数据库 schema。

## 本次验收结果

- 离线回归：237 项，213 通过，24 项隔离 PostgreSQL 集成测试按离线工作流跳过；Ruff 与 `git diff --check` 通过。
- 真实 qwen3.8-27b → FastAPI → AG-UI：计数、金额与币种、写权限拒绝、伪造引用拒绝，4/4 通过。CSV 提供独立预期。验收报告在本地 `/tmp/operion-guardrails-structured-acceptance.json`。
- 本地开发 Gateway 已重建 Agent。内置浏览器验证客户总数 10、完整销售订单表 30 行、单行分页同时显示筛选总数 30/本页 1，以及客户总数 10/有单客户数 8/销售订单数 30。刷新后最终文字和已有历史完整恢复。
- 当前数据是 `interview-wwi-v1` 的公开样本快照。本次未重新运行在线 ERPNext/Twenty 验收或 PostgreSQL 集成组；在线验收脚本已迁移到新契约，导入检查通过。
- Langfuse 只读回查确认浏览器运行 `Ey2cy7J` 的两个校验节点均为 `GUARDRAIL / DEFAULT / STRUCTURED_EVIDENCE_SUPPORTED`，政策 `structured-evidence-v1`；[对应 Trace](https://cloud.langfuse.com/project/cmv41jt6h05egad0el9rcy2kh/traces/44cf2e3adc3838c45bbb0f86b5670265)。
