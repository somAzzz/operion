# E4 内部跟进任务合同 v1

状态：已通过隔离演示验收（2026-09-20）。唯一真实写入是 Twenty 内部 Task 创建及其 Company TaskTarget；不修改客户、订单、库存或 ERPNext。

## 固定业务范围

- `action_type`: `twenty.followup_task`
- `target.system`: `twenty`
- 经营主体：服务端授权的 `AI Demo GmbH`
- 客户：服务端范围内的唯一 canonical customer；模型不能传 Twenty Company ID
- 订单：从已验证的履约 case 解析为唯一 ERPNext Sales Order；模型不能传订单 ID
- 负责人：服务端固定的一个有效 Twenty Workspace Member；模型不能选择负责人
- 状态：创建为 `TODO`
- 正文：模型建议的内部正文，加服务端生成的 ERPNext order 和 fulfillment case 引用
- 到期时间：必须带时区，且位于未来 30 天内
- 批准窗口：默认 30 分钟

允许的声明副作用固定为：

```text
twenty_internal_task
twenty_company_link
twenty_timeline_activity
```

当前单成员隔离 workspace 没有 Notification GraphQL 对象或数据库表，真实验收只观察到每个 Task 一条内部 `recordCreated` timeline activity，没有创建 outbound message。若增加成员、邮件集成、workflow 或通知子系统，必须重新探针，不沿用本结论。

## 提案和审批

Agent 只暴露 `propose_followup_task(case_id, title, body, due_at)`。服务端重新读取履约结果，只允许 `shortfall`，解析客户和订单映射，固定负责人和副作用，并对以下当前事实生成 SHA-256 precondition：

- Twenty Company ID、canonical external ID、`updatedAt`
- Workspace Member ID 和有效状态
- ERPNext Sales Order ID、customer、`modified`、`docstatus`、status

工具只写 Operion PostgreSQL 的 `PENDING_APPROVAL` 提案。幂等键是可信 conversation/run ID 的固定长度 SHA-256 摘要，不由模型选择。通用 Action API 拒绝客户端直接提交 `twenty.followup_task`，E4 提案也不能经通用修订接口换目标；内容需要变化时，必须从当前事实重新生成新提案。提案人不能审批自己的动作；审批请求只引用 `action_id + revision + decision + request_id`，执行参数始终从不可变修订读取。

## 执行与幂等

Worker 是唯一持有 Twenty 写密钥的进程。发送前重新计算 precondition；公司、订单、负责人、权限或版本变化均进入 `CONFLICT`，不发送。

Twenty Task ID 等于 Operion `action_id`。TaskTarget ID 为基于 action UUID 和固定名称生成的 UUIDv5。Worker 不使用 Twenty `upsert=true`：实测相同内容 upsert 会产生额外 update timeline activity。执行算法为：

1. 按确定性 Task/TaskTarget ID 精确回读。
2. 已存在则逐字段核对 title、markdown body、dueAt、status、assignee 和 Company 关联。
3. 不存在才执行普通 `createTask` / `createTaskTarget`。
4. 冲突、超时或断连后进入 `UNKNOWN`，不盲目重发。
5. 对账按同一 ID 回读；Task 已存在但 TaskTarget 缺失时，只补齐确定性 Target。
6. 内容不符、软删除或多个匹配进入 `MANUAL_REVIEW`。

Task 与 TaskTarget 是两个目标 API 写入，不宣称跨请求原子性；确定性 ID、精确回读和受限补齐提供可恢复的部分成功语义。

## 回读成功条件

只有以下条件全部满足才记录 `SUCCEEDED`：

- 唯一 Task ID 等于 action ID，未删除；
- title、markdown body、负责人、`TODO` 状态和到期时间与批准修订一致；
- 唯一 TaskTarget ID 正确，指向该 Task 和批准的 Company；
- Worker 在 Operion 动作账本保存 remote reference 和结果摘要。

Twenty 将时间精度规范化到毫秒，比较按该平台精度执行。浏览器成功文案和聊天历史不构成成功证据。

## 取消与补偿

发送前可取消；发送后取消请求只记录为在途请求，继续对账。E4 不向 Agent 开放 Task update/delete。验收或错误 Task 由授权人员在 Twenty 的正常业务界面标记 `DONE`，保留原创建和更新时间线；不能删除数据库记录掩盖事实。未来自动关闭属于新的写动作合同。
