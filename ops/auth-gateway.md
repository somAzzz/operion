# Local authentication gateway runbook

Original scope: 2026-09-29; current guidance reconciled 2026-11-08. I07 local Keycloak, public WWI snapshot, read-only Agent. Development/protocol acceptance only, not real writes or E5 actual-user observation.

## 1. Topology and trust boundaries

```text
Browser -> HTTPS Nginx :8443 -> OAuth2 Proxy -> Next.js -> Agent API
               |                    |                       |
            Keycloak           Redis session         OIDC + server policy
                                                           |
                                                scoped tools / WWI snapshot
```

- OIDC Authorization Code + PKCE S256, state, nonce. Compose pins Keycloak 26.7.4 and OAuth2 Proxy 7.15.4.
- Browser holds only `__Host-operion_session`, Secure/HttpOnly/SameSite=Lax/Path=/; no access/refresh token. Private Redis stores session content.
- Nginx strips external authentication/forwarding headers; OAuth2 Proxy injects session-derived `x-forwarded-access-token`. Next.js accepts no browser token cookie or enterprise static-token fallback.
- Protected Next.js requests call `/api/identity` to check signature, active user, and current roles. Agent/Action API independently verify authority. Public GET/HEAD exceptions include `/login`, build assets, favicon, and content-free health; business pages/APIs remain protected. This replaces the obsolete blanket statement that every static resource requires login.
- `/api/identity` returns user/tenant/company/roles, never token/session ID. It grants no `agent_read`. Conversation requires `agent_read`; action pages require action roles; actual decisions remain backend-authorized. Navigation hiding is supplementary: see [navigation access](../docs/enterprise/navigation-access.md).
- Non-read browser requests require exact Origin. `/oauth2/sign_out` is same-origin POST only; it deletes Redis session, performs Keycloak back-channel logout, and redirects to fixed `/signed-out`.
- Only Nginx publishes `127.0.0.1:8443`; Web/Agent/Keycloak/Redis have no host ports. Keycloak admin paths are private. Agent uses a fixed relay to existing SGLang and has no business-write credential/Worker.
- Gateway login does not establish current business-object relations. Original I01 defects have separate repairs/regressions; full live acceptance remains in the [current queue](../docs/enterprise/improvement-plan.md). This stack uses public snapshots.

Sources: [Compose](../deploy/gateway/compose.yaml), [OAuth2 Proxy](../deploy/gateway/oauth2-proxy.cfg), [Nginx](../deploy/gateway/nginx.conf), [Web admission](../apps/web/proxy.ts), [backend identity](../src/operion_etl/enterprise_auth.py).

## 2. Initialize and start

Requires Docker Compose, project Python, free port 8443. Real queries also require existing SGLang on host port 30000 serving `qwen3.8-27b`; login/identity do not need the model.

```bash
.venv/bin/python scripts/gateway.py init
.venv/bin/python scripts/gateway.py up
.venv/bin/python scripts/gateway.py status
```

`init` creates a local CA/site certificate, random passwords, OIDC client/cookie secrets, realm, and scope policy in ignored `var/gateway/`: directory 0700, credentials 0600; only container import/public certificates need readable mounts. Existing directories are not overwritten; reinitialization is not lossless secret rotation.

Entry: `https://operion.localhost:8443`.

Generated site certificates last thirty days. Scripts do not modify OS/browser trust or rotate certificates automatically. Add `var/gateway/tls/ca.crt` to the test browser's dedicated development trust. Do not disable TLS validation or count warning bypass as acceptance. Recheck current certificate expiry/trust and renew deliberately; a historical certificate date does not prove today's certificate validity.

If `.localhost` resolution is unavailable, configure local `127.0.0.1`. Protocol tests override resolution only inside their process and still validate certificate/hostname; system DNS changes are unnecessary.

| Synthetic user | Scope | Purpose |
| --- | --- | --- |
| alice | Customer 65, supplier 7, `agent_read` | Legitimate read path |
| bob | Customer 60, no supplier, `agent_read` | Cross-user/scope isolation |
| unassigned | No Operion policy | Valid IdP login grants no automatic business access |

Passwords stay in `var/gateway/credentials.json`, never terminal/log/report output. Synthetic accounts do not count as actual E5 users. Self-registration, password grants, and service-account grants are disabled.

```bash
curl --noproxy '*' --resolve operion.localhost:8443:127.0.0.1 \
  --cacert var/gateway/tls/ca.crt -o /dev/null -s -w '%{http_code}\n' \
  https://operion.localhost:8443/api/conversations
# Unauthenticated API: 401; protected home page: redirect to login.
```

`up` means containers created, not OIDC ready. Keycloak cold start may restart the proxy; acceptance waits for readiness. Stop only this stack:

```bash
.venv/bin/python scripts/gateway.py stop
```

Existing business/model/database containers are unaffected. Stop does not delete identity database or conversation history. Redis is not persisted; restarting it requires relogin.

## 3. Permission, revocation, and logout

Edit `var/gateway/policy/identity-policy.json` without restart. Prefer a same-directory temporary file followed by atomic replacement, preserving 0600. Compose mounts the directory so replaced files remain visible.

- `active=false`: deny subsequent user pages/API.
- `valid_after`: reject tokens issued before the Unix timestamp.
- `revoked_sessions`: deny matching token `sid`/`jti`.
- `customer_ids`, `supplier_ids`, `roles`: authority comes from server policy, not browser/model/self-reported JWT business roles.

Policy is resolved on each request; logout does not automatically recall in-flight work, which keeps its timeout. Access tokens last five minutes; proxy refresh attempts occur each minute. IdP-only revocation does not immediately invalidate every issued JWT. Use server revocation for immediate denial of subsequent Operion requests.

Use **Session / sign out**, then submit Sign out. Denied users also have an exit. Replaying a cookie cannot restore a deleted Redis session. Password autofill/new IdP login is not proof of the old session's survival. API 401 navigates once to a public expiry landing without mounting chat or replaying POST; see [session recovery](../docs/enterprise/session-expiry-login.md).

## 4. Reproducible acceptance

Use local synthetic identities only. The script temporarily changes Alice policy, creates demo conversations, and restores policy in `finally`. Do not run concurrently against an actively used policy or point it at real identities.

```bash
.venv/bin/python scripts/verify-gateway.py --model \
  --output reports/enterprise/improvements/gateway/protocol.json
scripts/verify.sh offline
scripts/verify.sh web
```

Without `--model`, no model/cross-user Agent conversation is exercised. Checks include TLS, actual login, PKCE/state/nonce, anonymous API, forged headers/token cookies, roles, revocation, CSRF, runtime port exposure, logout, and replay. Reports exclude passwords/codes/tokens/cookies. Model mode adds SSE and history isolation, not general factual accuracy grading.

Logs retain method/route category/status/duration. Raw Nginx errors/OAuth diagnostics are disabled because callbacks/tokens may appear. Inspect container status, sanitized gateway codes, and discovery health first; do not enable raw authentication logs in shared terminals.

Browser acceptance remains a separate matrix: trusted current CA → login → conversation → refresh → switch account → logout → back/replay → denied-user logout. Mark unavailable browser checks NOT RUN. Existing bounded session/navigation checks do not replace the full matrix. The [original gateway acceptance](../docs/enterprise/gateway-acceptance.md) remains dated evidence.

## 5. Move to actual identity infrastructure

Local Keycloak `start-dev`/H2, synthetic users, local CA, and single Redis are not production configuration.

1. Pin actual HTTPS domain/certificate/issuer; align callback, client, Host/Origin, public origin, issuer/audience/JWKS. No broad callback wildcards.
2. Use actual subjects and minimum policy; securely inject/rotate secrets. Revalidate old tokens/sessions/revocation after changes.
3. Use suitable IdP database/backup/session/failure strategy; pin image digests and code/config versions.
4. Prove no ingress bypass on the actual network. Existing host business/model ports are not automatically hardened by this stack.
5. Repeat protocol/browser/O01/O02, then begin scoped actual-user read-only observation. Real writes still require independent approval and specific acceptance.

References: [OAuth2 Proxy configuration](https://oauth2-proxy.github.io/oauth2-proxy/configuration/overview/), [session storage](https://oauth2-proxy.github.io/oauth2-proxy/configuration/session_storage/), [Keycloak containers](https://www.keycloak.org/server/containers), [reverse proxy](https://www.keycloak.org/server/reverseproxy).
