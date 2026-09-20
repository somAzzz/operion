# E5 企业试运行运行手册

本手册用于真实企业环境。示例值不能作为通过证据；敏感 evidence 和身份策略不得提交 Git。

## 1. 企业身份

从 `config/identity-policy.example.json` 复制受控文件，填写 3–5 名实际试运行用户、一个经营主体、customer scope 和最小角色。文件权限限制给服务账号，变更走双人复核。

```bash
export OPERION_ENVIRONMENT=enterprise
export OPERION_OIDC_ISSUER='https://id.example.com/real-tenant'
export OPERION_OIDC_AUDIENCE='operion'
export OPERION_OIDC_JWKS_URL='https://id.example.com/real-tenant/.well-known/jwks.json'
export OPERION_OIDC_ALGORITHMS='RS256'
export OPERION_IDENTITY_POLICY='/run/secrets/operion-identity-policy.json'
```

可信 ingress 必须覆盖并清除外部传入的 `x-forwarded-access-token`，再注入已登录会话的 token；Next.js 不能从公网绕过 ingress。验证错误 issuer、audience、签名、过期 token、禁用用户、`valid_after` 和 revoked session 全部被拒绝。

## 2. 只读与写入发布

首次启动保持：

```bash
export OPERION_WRITES_ENABLED=0
export OPERION_ENABLE_FOLLOWUP_PROPOSALS=0
```

完成 M3 后可运行真实数据只读试运行。只有 M4 证据签署后才能设置：

```bash
export OPERION_WRITES_ENABLED=1
export OPERION_ENABLE_FOLLOWUP_PROPOSALS=1
export OPERION_RELEASE_ID='<immutable-release-id>'
```

Action API、Agent、Worker 分别使用独立数据库/业务凭据和进程身份。Worker 与 PostgreSQL、SGLang、Twenty/ERPNext 私有接口不对普通客户端开放。

## 3. 监控与告警

用 `action_operator` token 拉取 `/api/operations`。至少采集状态计数、`oldest_unknown_seconds`、`expired_leases`、Worker `updated_at`、全局/工具暂停状态，并结合主机磁盘、数据库连接、上游错误和备份新鲜度。

立即告警：越权、重复副作用、审计断裂。5 分钟告警：UNKNOWN/RECONCILING、Worker 心跳停滞或业务时段错误率超过 5%。备份超过 15 分钟 RPO、磁盘余量低于确认阈值也告警。必须人工触发 PostgreSQL 失败、Worker 停滞和磁盘不足三类告警，并保存主/备联系人实际收到及处置的时间。

## 4. 保留与删除

每小时运行：

```bash
uv run operion-session-purge \
  --database "$OPERION_SESSION_DB" \
  --raw-content-hours 24
```

诊断日志最多 14 天、trace 最多 7 天、动作/批准事件至少 180 天；企业负责人可设更短原始内容期限或合法保留例外。每月执行一次删除抽查和访问审计抽查。

## 5. 备份与恢复

动作 PostgreSQL 的 RPO 目标为 15 分钟，仅 `pg_dump` 不满足该目标；生产环境应启用受监控的 WAL 连续归档和定期 base backup，并把加密副本保存到运行主机以外。会话 SQLite、identity policy、identity map、部署配置和版本清单一并备份，密钥通过独立渠道恢复。

恢复演练先在控制面关闭写入并停止 Worker，恢复到隔离网络，记录备份恢复点、开始/结束时间和缺失窗口。恢复后：

1. 验证动作事件链、身份策略和暂停开关；
2. 对备份点以来的 `EXECUTING/UNKNOWN/RECONCILING` action 按 action ID 回读 Twenty；
3. 确认旧 `APPROVED` 不被自动执行；
4. 重跑 E1–E4 回归；
5. 经业务与运维确认后才重新开放 Worker。

## 6. 容量、发布与 10 日观察

以五个并发会话测试读请求、Agent、批准任务和恢复队列，记录样本量、p50/p95、错误、GPU/CPU/内存和业务 API 负载。发布前固定代码 commit、镜像 digest、Python/Node lock、模型 revision、提示词/策略版本和迁移；保留上一可运行组合，实际演练失败回退。

连续至少 10 个业务日记录合法请求数、完成率、人工处理时间、p95、事实质量、审批积压、UNKNOWN、告警、备份、事故和业务收益。零流量或全拒绝不算通过。

把 `config/e5-evidence.example.json` 复制到忽略目录并替换所有占位符，再执行：

```bash
uv run operion-evaluate-e5 \
  --evidence reports/enterprise/e5/<run-id>/evidence.json \
  --output reports/enterprise/e5/<run-id>/evaluation.json
```

只有退出码 0 且 `status=passed`，并有业务、运维、治理三方真实签署，才能把 E5 标记为 PASSED。
