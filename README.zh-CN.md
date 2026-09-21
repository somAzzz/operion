# Operion

[English](README.md) | 中文

建立在 Twenty 和 ERPNext 之上的受控业务 Agent 层。Agent/MCP 是主线，业务系统与轻量 ETL 提供事实和工具支撑。

目标：让人掌握必要的业务判断，让 agent 协助查询、整理、建议和受控执行。

![Operion 系统架构](docs/imgs/pipeline.png)

当前阶段：**E0–E4 已通过，下一步进入 E5 企业试运行**。
WWI 下载与最小 ETL 已实现；Twenty 已回读 10 个 WWI Company 和 25 个 People，
其中 18 个 People 具备预期 Company 关联；ERPNext 已回读并核对 8 个客户、2 个供应商、
9 个商品、25 个联系人、8 张销售订单和 2 张采购订单。双系统 identity map 已完成
ERPNext 72/72、Twenty 35/35 回读；客户概览和履约检查已作为仅有的两个只读 MCP 工具
通过 15 个固定 E1 案例。E2 已实现本地 SGLang/Pydantic AI Agent、AG-UI
接入、服务端可信会话与 assistant-ui 证据界面；15 个案例各重复 3 次全部通过，
并在 E2 阶段保持业务写入关闭。E3 已实现 PostgreSQL 动作账本、可信独立审批、租约、
未知结果对账、W01–W15 故障验证，以及 `/approvals`、`/actions` 状态页面；
E4 已在隔离 Twenty 2.39.0 的公开/模拟数据上验证单一内部 Task 创建、确定性
Task/TaskTarget ID、独立审批、精确回读和断连/崩溃恢复。真实写入仍仅限该隔离演示；
企业身份、真实数据、告警和发布控制须通过 E5。

面试演示现包含两套互不覆盖的数据：固定 seed 的纯模拟
`interview-demo-v1`，以及从 SHA-256 固定的 WWI v1 公开样例中按完整订单规则
确定性抽取的 `interview-wwi-v1`。两套数据均支持客户/供应商搜索、销售/采购订单
列表与详情；首个写操作仍仅限经过独立审批的内部跟进任务。

推进顺序：用例与预期答案 → 小样本导入 → 只读适配器 → 业务工具/MCP → Agent 与评估 → 单一受控写入 → 按需同步。

## 文档入口

- [企业运行方案与阶段子方案](docs/enterprise/README.md)：从环境基线、assistant-ui 前端、只读 Agent、受控写入到企业试运行的完整设计、阶段子目标与验收标准。
- [人工功能与 agent 设计对照](docs/human-functions-agent-map.md)：需要了解哪些业务功能，哪些判断交给人。
- [Agent / MCP 边界](docs/agent-boundaries.md)：工具范围、权限、审批和验证要求。
- [最小演示与评估](docs/minimum-demo.md)：固定业务日期、履约口径、15 个案例与退出条件。
- [E2 Agent 运行手册](ops/e2-agent.md)：固定版本、启动、评测、恢复与限制。
- [E3 动作控制合同](contracts/e3-action-control-v1.md)：动作 schema、状态机、审批与恢复保证。
- [E3 动作控制运行手册](ops/e3-action-control.md)：部署、验收、暂停与故障处置。
- [E4 跟进任务合同](contracts/e4-followup-task-v1.md)：唯一真实写入的固定范围与保证。
- [E4 跟进任务运行手册](ops/e4-followup-task.md)：凭据隔离、审批、恢复与补偿。
- [E5 企业边界合同](contracts/e5-enterprise-boundary-v1.md)：OIDC、服务端范围、撤销、发布锁和证据门禁。
- [E5 企业试运行手册](ops/e5-enterprise-pilot.md)：告警、备份恢复、容量、回退和 10 日观察。
- [数据目录说明](data/README.md)：原始数据、加工数据和导出结果的保存规则。
- [面试模拟数据运行手册](ops/interview-demo-data.md)：虚构 DEMO 数据的生成、校验和受控装载。
- [WWI 面试数据运行手册](ops/interview-wwi-data.md)：公开样例的固定抽取、血缘、校验和受控装载。

## 目录

```text
operion/
├── docs/                     # 方案、功能对照、边界和路线
├── data/
│   ├── raw/                  # 原始来源快照：wwi / adventureworks / ema / openfda
│   ├── staging/              # 可选中间结果，不要求第一版落盘
│   ├── canonical/            # 统一业务模型数据
│   ├── exports/              # erpnext / twenty 导入文件
│   └── quarantine/           # 错误文件；完整复核工作流后置
├── mappings/                 # 字段、枚举、单位和标识映射
├── contracts/                # 数据与工具接口合同
├── evaluations/              # 业务问题、权限与异常验收案例
├── reports/                  # 数据质量、对账和 agent 评估结果
└── ops/                      # 环境基线、运行与恢复说明
```

实际数据与运行输出默认不纳入版本管理。当前业务代码集中在独立的数据流水线；后续模块将按 integrations、业务工具/domain、MCP 和 agent 分层。

## 数据流水线

运行方式和重跑约束见 [WWI 下载与 ETL 运行手册](ops/data-pipeline.md)，
统一模型见 [Canonical 数据合同](contracts/canonical-v1.md)。生成的数据与报告
按 `.gitignore` 保持在本地，不纳入版本控制。
