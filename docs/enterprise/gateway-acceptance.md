# I07 local authentication gateway acceptance

Date: 2026-09-29. Historical status: **LOCAL_PROTOCOL_PASSED / BROWSER_NOT_RUN**. The user selected local Keycloak. Scope was the independent loopback deployment, synthetic identities, and public WWI snapshot.

Later bounded [session-recovery](session-expiry-login.md) and [navigation](navigation-access.md) browser checks do not overwrite this run's NOT RUN result or complete I07/E5. Current remaining work is in the [improvement plan](improvement-plan.md).

## Delivered

- Nginx 1.30.5 HTTPS, Keycloak 26.7.4, OAuth2 Proxy 7.15.4, Redis 7.4.11 server sessions, private Web/Agent; only `127.0.0.1:8443` published.
- Code flow, PKCE S256, state/nonce, Secure/HttpOnly/SameSite cookie, server token forwarding, independent backend checks.
- Current identity/role policy per protected request; no enterprise browser-token-cookie fallback; identity lookup granted no extra role.
- Same-origin mutations and POST sign-out deleting Redis session and ending Keycloak session.
- Init/start/stop, reproducible protocol checks, health/readiness dependencies, denied-page exit, runbook, regressions.

See [runbook](../../ops/auth-gateway.md). Entry `https://operion.localhost:8443`; secrets stayed in ignored `var/gateway/credentials.json`; the test browser needed dedicated development CA trust.

## Results from this run

| Check | Result | Scope |
| --- | --- | --- |
| Real Keycloak/HTTPS protocol | 38/38 PASS | `scripts/verify-gateway.py --model`, including real model request |
| Python | 169: 146 PASS, 23 SKIPPED, 0 FAIL | Isolated database unavailable; explicit skips |
| Web build | PASS | Docker `npm run build -- --webpack` and TypeScript |
| Python lint/diff | PASS | Changed Python Ruff; `git diff --check` |
| Browser rendering/clicks | NOT RUN | No browser/app in Computer Use inventory; HTTP/SSE did not substitute |
| Actual-user E5 observation | NOT RUN | Synthetic identities were not actual users; no ten-business-day observation |

The 38 checks covered anonymous redirect/API 401; forged headers/token cookies; Host/admin paths; runtime port isolation; direct forged private Web/Agent requests; PKCE/state/nonce; callback replay; secure cookies/no rendered token; legitimate pages/APIs; cross-origin/missing Origin; valid IdP user without policy; disable/restore; wrong role; old-login revocation; real Agent SSE; cross-user history; signed-out cookie replay and IdP termination.

Restart initially exposed login before backend readiness. Health dependencies repaired ordering and the final run passed. Initial failures were retained, not deleted. Final evidence used the pinned updated Nginx/Redis and final Web/Agent builds.

Local ignored evidence:

```text
reports/enterprise/improvements/gateway/
  acceptance-final.json           final 38 results/timestamps
  manifest.json                   baseline, changed-file hashes, images, environment
  initial.json                    early restart-interference failure
  acceptance.json                 backend-not-ready failure
  acceptance-after-readiness.json post-readiness-fix run
```

No password, OAuth code, token, or cookie was published. Temporary test policy edits were restored in `finally`. No Action Worker or target business writes ran; new data stayed in stack identity/session/history/evidence stores.

## Unreleased scope at this checkpoint

- Browser clicks/CA trust still required actual testing; only protocol/service behavior was established.
- I01 relation, I02 grading, and I03 fulfillment defects were not repaired by this gateway work. Later separate fixes do not change this run's scope; login does not replace object authorization.
- Keycloak used start-dev/H2; Redis was unpersisted. Actual deployment needed identity database/backups, key/certificate rotation, monitoring, and recovery.
- Stack isolation did not prove existing host model/business/database network isolation.
- Logout/revocation blocked subsequent requests; in-flight requests retained timeout. IdP revocation did not replace server policy.
- This run did not mark full I07 PASSED, release E5/M3, enable real writes, or approve private data.
