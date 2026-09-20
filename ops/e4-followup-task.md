# E4 内部跟进任务运行手册

E4 在 E3 动作账本上启用唯一真实适配器 `twenty.followup_task`。仅用于公开/模拟数据的隔离演示 workspace。

## 凭据隔离

三个进程使用不同能力：

- Agent：只读 Twenty/ERPNext 凭据和受限动作数据库身份；只能创建提案。
- Action API：动作数据库身份；不持有 Twenty 写密钥。
- Worker：动作数据库身份、Twenty 专用写密钥和 ERPNext 只读密钥。

Agent 不读取包含管理员 key 的 `.env` 文件。启用提案前，把只读值作为该进程的环境变量显式注入：

```bash
export OPERION_ENABLE_FOLLOWUP_PROPOSALS=1
export OPERION_ACTION_DATABASE_URL='postgresql://restricted-action-login@...'
export OPERION_ACTION_TENANT_ID='operion-demo'
export OPERION_FOLLOWUP_ASSIGNEE_ID='<fixed Twenty workspace-member UUID>'
export TWENTY_API_KEY_READ_ONLY='<read-only key>'
export ERPNEXT_API_KEY_READ_ONLY='<api-key:api-secret>'
# 同时设置 E2 的 canonical、identity map、scope 和 observation 环境变量
uv run operion-agent
```

Action API 的提案人和审批人必须是不同服务端身份。审批人配置示例：

```bash
export OPERION_ACTION_USER_ID='e4-approver'
export OPERION_ACTION_TENANT_ID='operion-demo'
export OPERION_ACTION_COMPANIES='AI Demo GmbH'
export OPERION_ACTION_CUSTOMER_IDS='operion:e2:organization:customer:ambiguous-a'
export OPERION_ACTION_CAN_APPROVE=1
uv run operion-action-api
```

Worker 才能读取 `.env` 中的 `TWENTY_API_KEY`：

```bash
export OPERION_ACTION_DATABASE_URL='postgresql://restricted-action-login@...'
uv run operion-action-worker --once --worker-id e4-worker-1
```

不要把写 key 配置到 Next.js、Agent、MCP 或 Action API。

## 操作流程

1. Agent 先运行 `check_fulfillment`，只对确定的 `shortfall` 调用 `propose_followup_task`。
2. 在 `/approvals` 核对 Company、ERPNext order、负责人、title/body、dueAt、修订、摘要和三项副作用。
3. 由不同身份批准 exact revision。
4. Worker 原子领取并在发送前复核当前 Company、order 和 assignee。
5. `/actions/{action_id}` 观察事件；只有 `SUCCEEDED` 才打开 Twenty Task 链接。

`UNKNOWN`、`RECONCILING` 或 `MANUAL_REVIEW` 时禁止重新提案或手工重复创建。恢复租约过期动作：

```bash
uv run operion-action-worker --recover --worker-id e4-recovery-1
```

立即对账一个 `UNKNOWN/RECONCILING` 动作：

```bash
uv run operion-action-worker --reconcile <action_id> --worker-id e4-recovery-1
```

## 验收复现

准备隔离 PostgreSQL，按 E3 手册运行迁移，然后：

```bash
export OPERION_TEST_ACTION_DATABASE_URL='postgresql://...'
uv run ruff format --check src tests
uv run ruff check .
uv run python -m unittest discover -s tests -q
uv run operion-evaluate-e4 \
  --database-url "$OPERION_TEST_ACTION_DATABASE_URL" \
  --live-report reports/enterprise/e4/20260920T-followup-task/live-fault-evaluation.json \
  --output reports/enterprise/e4/20260920T-followup-task/w01-w15.json
cd apps/web && npm run build
```

真实故障演练必须使用新的 action ID，并确认：批准前不存在 Task；响应丢失后为 `UNKNOWN`；按 action ID 回读恢复；双 Worker 仅一方领取；租约过期先对账；Task 和 TaskTarget 各唯一且字段完全匹配。

## 暂停、异常与补偿

- 发现错误目标、重复 Task 或未知外部通知：立即暂停 `twenty.followup_task`。
- precondition 变化：保留 `CONFLICT`，重新生成提案，不覆盖旧批准。
- Task 内容或确定性 ID 不符：保持 `MANUAL_REVIEW`，比较 Twenty 与动作修订。
- Task 已创建但 Target 缺失：只允许 recovery 按确定性 Target ID 补齐。
- 验收/错误 Task：授权人员在 Twenty 标记 `DONE`；记录 action ID 和原因，不数据库删除。
- 新增成员、邮件、workflow 或通知能力后，在恢复写入前重跑 side-effect probe。

E4 通过只授权隔离演示的内部 Task 创建。企业登录、真实数据、长期审计备份、告警和发布流程属于 E5。
