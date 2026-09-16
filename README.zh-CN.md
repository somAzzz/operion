# Operion

[English](README.md) | 中文

建立在 Twenty 和 ERPNext 之上的受控业务 Agent 层。Agent/MCP 是主线，业务系统与轻量 ETL 提供事实和工具支撑。

目标：让人掌握必要的业务判断，让 agent 协助查询、整理、建议和受控执行。

![Operion 系统架构](docs/imgs/pipeline.png)

当前阶段：**WWI 下载、最小 ETL 与 Twenty Company 小批次导入已实现**。
已生成可复现的公开样例、目标映射文件和验证证据；Twenty Company UUID
已通过 REST 回读写入 identity map，People CSV 已准备但尚未导入，ERPNext 与
agent 尚未实现。

最小演示：客户概览入口＋履约检查主场景＋15 个评估案例。先以小样本和只读适配器连接 Agent，持续同步后置；首个写操作仅创建内部跟进任务。

推进顺序：用例与预期答案 → 小样本导入 → 只读适配器 → 业务工具/MCP → Agent 与评估 → 单一受控写入 → 按需同步。

## 文档入口

- [企业运行方案与阶段子方案](docs/enterprise/README.md)：从环境基线、只读 Agent、受控写入到企业试运行的完整设计、阶段子目标与验收标准。
- [人工功能与 agent 设计对照](docs/human-functions-agent-map.md)：需要了解哪些业务功能，哪些判断交给人。
- [Agent / MCP 边界](docs/agent-boundaries.md)：工具范围、权限、审批和验证要求。
- [最小演示与评估](docs/minimum-demo.md)：固定业务日期、履约口径、15 个案例与退出条件。
- [数据目录说明](data/README.md)：原始数据、加工数据和导出结果的保存规则。

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
