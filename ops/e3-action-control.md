# E3 动作控制运行手册

E3 运行 Action Service、PostgreSQL 动作账本和独立 Worker。Worker 只调用持久化测试桩，不写 Twenty 或 ERPNext。

## 环境与迁移

使用 PostgreSQL 16 或兼容版本。迁移身份与日常服务身份必须分开：迁移身份能创建/授予无登录角色 `operion_action_app`；日常 DSN 只能继承或切换到该受限角色，不拥有 schema/table，也没有迁移权限。托管数据库若禁止 `CREATE ROLE`，由平台管理员预建同名角色后再运行迁移。

```bash
uv sync --extra dev
export OPERION_ACTION_MIGRATION_DATABASE_URL='postgresql://migration-admin@...'
uv run operion-action-migrate

export OPERION_ACTION_DATABASE_URL='postgresql://restricted-action-login@...'
# 仅当受限登录需要显式 SET ROLE 时设置：
# export OPERION_ACTION_DATABASE_ROLE='operion_action_app'
export OPERION_ACTION_TOKEN='replace-with-secret'
export OPERION_ACTION_CSRF_TOKEN='replace-with-separate-secret'
export OPERION_ACTION_USER_ID='e3-local-user'
export OPERION_ACTION_TENANT_ID='e3-local-tenant'
export OPERION_ACTION_COMPANIES='AI Demo GmbH'
export OPERION_ACTION_CAN_APPROVE='0'
uv run operion-action-api
```

Action API 和 Worker 不自动迁移数据库。审批服务应使用独立用户与凭据，并显式设置 `OPERION_ACTION_CAN_APPROVE=1`；默认值为 `0`。生产凭据不得写入仓库或浏览器环境变量。当前 E3 单凭据环境入口用于本地验收；多用户认证应由接入层构造服务端 `Principal`。

健康检查必须返回 `mode=e3_stub_only` 和 `writes_enabled=false`：

```bash
curl http://127.0.0.1:8001/health
```

## Worker、暂停与恢复

运行一个领取周期：

```bash
uv run operion-action-worker --once --worker-id e3-worker-1
```

恢复所有租约过期的在途动作：

```bash
uv run operion-action-worker --once --recover --worker-id e3-recovery-1
```

恢复命令只做对账，不把过期租约当作未提交证据。`UNKNOWN`、`RECONCILING` 或 `MANUAL_REVIEW` 不能由操作员直接重置为待执行。暂停通过 `POST /api/action-pauses` 设置 `global` 或 `stub.followup_task` scope；恢复前记录原因并确认没有未完成对账。

## 验收

准备隔离 PostgreSQL 后运行：

```bash
export OPERION_TEST_ACTION_DATABASE_URL='postgresql://...'
uv run ruff format --check src tests
uv run ruff check .
uv run python -m unittest discover -s tests -q
uv run operion-evaluate-e3 \
  --database-url "$OPERION_TEST_ACTION_DATABASE_URL" \
  --output reports/enterprise/e3/20260920T-action-control/w01-w15.json
uv run operion-probe-e3 \
  --database-url "$OPERION_TEST_ACTION_DATABASE_URL" \
  --output reports/enterprise/e3/20260920T-action-control/capability-matrix.json
```

能力探针读取本地 `.env` 中的 Twenty 只读凭据，只执行 GraphQL schema introspection 和 `GET /rest/tasks`。它不会创建 Task。`capability-matrix.json` 必须保持 `e4_release_allowed=false`，直到 E4 的隔离写入探针全部通过。

Web 验收：

```bash
cd apps/web
npm run build
npm run dev
```

确认 `/approvals`、`/actions` 和 `/actions/{id}` 的状态均来自 Action Service；刷新页面后状态不丢失；`UNKNOWN/RECONCILING` 不提供重新创建捷径。

## 故障处置

- 数据库或审计写入失败：停止新动作，不绕过动作账本。
- 发现重复效果：立即启用全局暂停，保留动作、尝试、事件和下游记录证据。
- Worker 崩溃或租约过期：运行 recovery 对账，不启动第二次提交。
- 多个下游匹配或内容摘要不一致：维持 `MANUAL_REVIEW`，由系统负责人调查。
- 事件链校验失败：停止写入，保全数据库和应用日志，由独立管理员核查。

E4 之前仍需验证 Twenty Task 的 ID 唯一性、关联原子性、通知副作用、失败/超时语义以及精确回读；任一项未证明都不能开放真实写入。
