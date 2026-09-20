# E3 动作控制合同 v1

状态：已验收（2026-09-20）。本合同只允许持久化测试桩
`stub.followup_task`，不授权 Twenty 或 ERPNext 写入。

## 信任边界

- 客户端只提交动作引用、修订号和决定，不能提交审批人、租户、公司范围或替换执行参数。
- 身份、租户、经营主体范围和审批资格由 Action Service 的服务端凭据解析。
- 提案人不能审批或拒绝自己的提案；审批人与执行 Worker 分离。
- 所有 mutation 同时要求 bearer credential 和 `X-Operion-CSRF`。E3 的静态服务凭据只用于隔离验收；企业 Cookie/OIDC 会话留到 E5。
- Agent、浏览器和 Next.js 客户端都没有下游写凭据。E3 Worker 只能写 PostgreSQL 中的幂等测试桩。

## 固定动作结构

`ProposalRequest` 使用严格 schema，未知字段直接拒绝。允许值固定为：

- `action_type`: `stub.followup_task`
- `target.system`: `e3_stub`
- `side_effects`: 仅 `internal_stub_record`
- `target`: 公司、客户 ID、订单 ID
- `parameters`: 标题、正文、负责人 ID、带时区截止时间
- `preconditions.target_version`: 发送前必须重新验证的目标版本
- `expires_at`: 带时区的批准有效期
- `idempotency_key`: 同一租户、提案人和动作类型内唯一

同一幂等键与相同内容返回原 `action_id`；相同键不同内容返回冲突。每个修订保存规范化 JSON、SHA-256 内容摘要和策略版本。修改参数会产生新修订、回到 `PENDING_APPROVAL` 并使旧批准失效。

## REST 合同

```text
POST /api/action-proposals
GET  /api/actions?status=PENDING_APPROVAL
GET  /api/actions/{action_id}
GET  /api/actions/{action_id}/events
POST /api/actions/{action_id}/decisions
POST /api/actions/{action_id}/revisions
POST /api/actions/{action_id}/cancel
POST /api/action-pauses
```

决定请求只包含 `revision`、`decision`、`request_id` 和可选原因。`request_id` 对审批人幂等；旧修订、过期批准、提案人自批、跨租户或跨公司访问均失败。跨范围查询统一返回未找到，避免泄露记录存在性。

## 状态与执行保证

```text
PENDING_APPROVAL -> APPROVED -> EXECUTING -> SUCCEEDED
       |              |             |
       |              |             +-> UNKNOWN -> RECONCILING
       |              |                                |-> SUCCEEDED
       |              |                                |-> APPROVED（确认未提交）
       |              |                                +-> MANUAL_REVIEW
       |              +-> REVOKED / CONFLICT / CANCELLED
       +-> REJECTED / EXPIRED / CANCELLED
```

- Worker 通过 `FOR UPDATE SKIP LOCKED` 原子领取，写入尝试和租约。
- 发送前复核经营主体、负责人、提案人权限和目标版本，并再次检查暂停开关。
- 只有能证明未提交的失败才回到 `APPROVED`；响应丢失或远端提交窗口崩溃进入 `UNKNOWN/RECONCILING`。
- 租约过期不触发第二次写入，而是先按稳定 `action_id` 对账。
- 零个结果可安全重试，一个匹配且摘要一致可恢复成功，多个或摘要不一致进入 `MANUAL_REVIEW`。
- 补偿是引用原成功动作的新动作和新审批；原成功事实不被改写。

## 持久化与审计

PostgreSQL 保存动作、不可变修订、不可变决定、执行尝试、暂停状态、追加事件和测试桩效果。事件包含前一事件摘要，形成每个动作的哈希链。运行角色 `operion_action_app` 对修订、决定和事件没有 UPDATE/DELETE 权限；迁移由独立的高权限身份和显式命令执行，Action API/Worker 启动不会自动迁移。

该哈希链用于检测普通数据库改写，不等同于外部不可篡改存储。管理员审计、独立备份和保留策略属于 E5。

## E4 放行边界

E3 的成功只证明控制面和持久化测试桩；当时的能力报告保持 `e4_release_allowed=false` 作为历史证据。后续 E4 已在隔离对象上完成客户端指定 ID、TaskTarget 恢复、timeline 副作用、连接丢失及精确回读验证，实际放行范围以 [E4 跟进任务合同](e4-followup-task-v1.md) 为准。
