# E5 single-operator read-only pilot runbook

For one actual user, locally or hosted, with explicit public-sample or approved private-data scope. Examples are not passing evidence. Sensitive evidence/identity policy stay out of Git. Single-user acceptance establishes neither actual multiple-user load isolation nor backup staffing. See the [current queue](../docs/enterprise/improvement-plan.md).

## 1. Enterprise identity

The [local Keycloak gateway](auth-gateway.md) supports public-snapshot protocol acceptance. It does not automatically establish actual-user/full-browser/E5 operation. Repeat applicable identity/network checks in the actual environment; bounded session/navigation browser records are separate evidence.

Copy `config/identity-policy.example.json` into a controlled file. Enter one actual user/company/customer scope/minimum roles; restrict access to service accounts. Record before/after change summaries, time, and self-check. Separate controlled identities test cross-user/tenant behavior and do not count as actual pilot users.

```bash
export OPERION_ENVIRONMENT=enterprise
export OPERION_OIDC_ISSUER='https://id.example.com/real-tenant'
export OPERION_OIDC_AUDIENCE='operion'
export OPERION_OIDC_JWKS_URL='https://id.example.com/real-tenant/.well-known/jwks.json'
export OPERION_OIDC_ALGORITHMS='RS256'
export OPERION_IDENTITY_POLICY='/run/secrets/operion-identity-policy.json'
```

Ingress strips external `x-forwarded-access-token` and injects the authenticated session token. Next.js cannot be publicly reached around ingress. Reject wrong issuer/audience/signature, expiry, disabled user, `valid_after`, and revoked session.

## 2. Read-only and write release

Initially retain:

```bash
export OPERION_WRITES_ENABLED=0
export OPERION_ENABLE_FOLLOWUP_PROPOSALS=0
```

After identity/scope/network/read-safety prerequisites, begin read-only observation. Only completed observation and the other evidence establish M3. The E5 evidence field uses `data_mode=public_sample` or `private` (distinct from a read adapter's snapshot/live mode); sample acceptance does not establish private-data acceptance. Single-user E5 does not authorize the following settings: they require an independent approver, M4-specific acceptance, and confirmed operating hours.

```bash
export OPERION_WRITES_ENABLED=1
export OPERION_ENABLE_FOLLOWUP_PROPOSALS=1
export OPERION_RELEASE_ID='<immutable-release-id>'
```

Separate API/Agent/Worker process and database/business identities. Ordinary clients cannot reach Worker, PostgreSQL, SGLang, or private business APIs.

## 3. Monitoring and alerts

Read `/api/operations` with `action_operator`. Collect state counts, `oldest_unknown_seconds`, `expired_leases`, Worker `updated_at`, pauses, host disk, connections, upstream errors, and backup freshness. Deliver alerts to the actual operator and record response hours. Stop/pause Worker when unattended; do not claim 24-hour staffing.

Immediately alert on unauthorized/duplicate effects or audit gaps. Alert after five minutes for UNKNOWN/RECONCILING, stalled Worker, or >5% errors during operating hours. Also alert beyond fifteen-minute backup RPO or the confirmed disk threshold. Trigger database failure, stalled Worker, and low-disk drills and retain actual receipt/response times.

## 4. Retention and deletion

Run hourly:

```bash
uv run operion-session-purge \
  --database "$OPERION_SESSION_DB" \
  --raw-content-hours 24
```

Operational policy: diagnostics at most fourteen days, traces seven days, action/approval events at least 180 days, subject to owner-approved shorter raw-content retention or lawful exceptions. Configure/verify each store; only session purge is implied by this command. Sample deletion/access audit monthly.

## 5. Backup and recovery

PostgreSQL target RPO is fifteen minutes; `pg_dump` alone is insufficient. Use monitored WAL/base backups or a verified alternative, with encrypted off-host copies. Back up SQLite, identity policy/map, deployment, and versions; recover keys separately.

Disable writes/Worker before restoring in an isolated network. Record backup point, start/end, and loss window, then:

1. Verify event chain, identity policy, pauses.
2. Read back Twenty by action ID for post-backup EXECUTING/UNKNOWN/RECONCILING work.
3. Prove old APPROVED actions do not auto-execute.
4. Rerun applicable E1–E4 regressions in isolation.
5. Restore Worker only after business/operator confirmation and specific write release.

## 6. Capacity, release, and ten-day observation

Generate five concurrent read/Agent sessions automatically. Test approval/recovery queues only in the isolated demo, never by writing actual data. Record count, p50/p95, errors, GPU/CPU/memory, and API load; sessions are not actual users. Pin commit, image digest, Python/Node locks, model revision, prompt/policy, and migrations. Keep the previous runnable combination and actually drill failed-release rollback.

For at least ten business days, one actual user records legitimate requests/completion, human time, p95, fact quality, approval backlog, UNKNOWN, alerts, backups, incidents, and benefit. Zero traffic, all refusals, or test-only traffic does not pass.

Copy `config/e5-evidence.example.json` to an ignored run directory and replace every placeholder:

```bash
uv run operion-evaluate-e5 \
  --evidence reports/enterprise/e5/<run-id>/evidence.json \
  --output reports/enterprise/e5/<run-id>/evaluation.json
```

Only exit 0, `status=passed`, actual operator self-signature, `writes_disabled=true`, and `operion-e5-evidence-v2` establish PASSED for single-user read-only E5. Old v1 evidence cannot be reused as v2. Multiple users, unattended operation, and every actual write need separate acceptance.
