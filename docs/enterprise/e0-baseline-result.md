# E0 实验环境基线验收结果

验收时间：2026-09-16；运行 ID：`20260916T205333Z`；结论：`PASSED`（实验环境）。

本结论只放行 E1 的受控只读建设，不代表 E1 已完成，也不开放任何 Operion 写入。详细证据和含敏感配置的备份保存在本地受控目录 `reports/enterprise/e0/20260916T205333Z/`，不提交 Git。

## 子目标结论

| 子目标 | 结论 | 主要证据 |
|---|---|---|
| E0.1 现状 | PASS | Twenty 回读 10 个 WWI Company、25 个 People，18 个 People 具备 Company 关联；ERPNext API 审计的 8/2/9/25/8/2 个核心对象与导出一致 |
| E0.2 版本和拓扑 | PASS | Twenty 2.39.0、ERPNext 16.34.2/Frappe 16.33.1、PostgreSQL 16.15、MariaDB 11.8.9、SQL Server 16.0.4275.2、SGLang 0.5.19；健康探针通过 |
| E0.3 凭据和权限 | PASS（收窄范围） | Twenty 只读 Key 已通过直接读取及创建/修改/删除负向测试；名为只读的 ERPNext Key 实际可写，禁止接入 Agent 或 E1 适配器 |
| E0.4 恢复 | PASS | Twenty PostgreSQL＋63 个存储文件、ERPNext 数据库＋文件、WWI 备份均恢复到隔离临时目标并核对；临时目标已清理 |
| E0.5 演示约定 | PASS | `fulfillment-v1` 固定为 2016-05-31、Europe/Berlin、`AI Demo GmbH`、`WWI Main Warehouse`、`Each`→`Unit`、`ship_by`，F01–F06 预期已版本化 |
| E0.6 绕行路径 | PASS（当前能力） | Twenty 内置 Helper 无写/删/全工具权限；不存在 Operion Agent、写执行器或其凭据；SGLang 未认证请求被拒绝 |

## 已验证基线

- 当前代码提交：`3ac3d946acb86c38727f8ed8311c7b6ef55f0a83`；验收时工作树包含本轮文档清理和状态更新。
- WWI 原始备份 SHA-256：`e842bad6ce02f74f166947e559dab1b476edd7eaae3da2ab9e3f522f1dd87124`。
- SGLang 模型：`RadixArk/Qwen3.8-27B-NVFP4`，修订 `554ebba9b5f1b79dc11246341960360e6ef05ef4`；工具调用、严格结构化输出和关闭 thinking 的探针通过。
- 本地 `.env` 权限已收紧为 `0600`；报告不记录密钥值。

## 明确限制与后续门槛

1. Twenty 现有 `test` API key 仍是 Admin，只归类为 ETL/管理凭据，禁止注入 Agent。2026-09-19 复验中，`TWENTY_API_KEY_READ_ONLY` 读取成功，创建、修改和删除均被服务端拒绝，临时测试数据已清理；该凭据可作为 E1 Twenty 只读适配器的候选凭据。
2. ERPNext 的角色权限是累加式。2026-09-19 复验中，`EPRNEXT_API_KEY_READ_ONLY` 虽能认证和读取，但有效权限仍允许 Customer/Contact 创建和修改，并允许 Sales Order/Purchase Order 创建、修改、删除、提交、取消和修订；直接 API 测试也完成了 ToDo 的创建、修改和删除，测试记录已清理并回读 404 确认。该凭据不是只读凭据，禁止注入 Agent 或 E1 适配器；E1 实际 ERPNext 接入前必须收窄账号角色并重跑直接写入负向测试，或建立独立的服务端只读边界。
3. ERPNext 自定义来源键当前不是数据库唯一约束，且订单父 DocType 存在冗余子字段。这不影响本次只读回读，但在 E1 对账和 E3 幂等探针中必须处理。
4. 最新 ERPNext 批次的 identity map 未写入目标 ID；现有 API 审计以来源键完成回读。E1.1 需补齐统一身份对照，不能仅依赖名称。
5. 端口 1433、3000、8080、9443、30000 当前绑定所有主机接口；服务自身鉴权已验证，但本轮无权限读取主机防火墙规则。企业试运行前必须验证网络策略并收窄 SGLang/数据库入口。

上述限制不会扩大当前能力：E1 只读工具通过前不连接 Agent，E3/E4 通过前不存在 Operion 写入路径。
