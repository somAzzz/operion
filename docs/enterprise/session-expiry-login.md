# Login navigation after session expiry

Implemented 2026-10-17. A business-request HTTP 401 triggers one full-page replacement to `/login?reason=session_expired`. The landing asks the user in English to log in again because the session expired or became invalid; it mounts no chat runtime and fetches no history, preventing a 401 loop. HTTP 403 and ordinary network errors retain their meanings.

The `(workspace)` group contains conversation/action/approval/session pages without changing URLs. Login and build assets allow anonymous GET/HEAD; ingress still strips external identity headers, and business routes retain authentication/authorization. Login continues through OAuth2 Proxy → Keycloak with a fixed `/` return target, never an external supplied destination.

Concurrent 401s cause one navigation. Keep local conversation identity/server history and never automatically replay interrupted POST. Previously open pages need a refresh to load the new client code.

## Recorded validation (2026-10-17)

- `npm run test:session`: 6 passed for concurrent 401, leaving workspace, 403, stream passthrough, network error, and no login-page loop. Requires Node.js 22.18+, consistent with Node 22 deployment/CI.
- Docker TypeScript/production build and Nginx configuration validation passed; Nginx was reloaded.
- Anonymous checks verified landing 200, correct CSS/JS types, business API 401, login POST 403, and fixed authenticated return target.
- In-app browser: briefly invalidated a local admin test token, clicked the existing conversation, observed actual 401/expiry landing, then restored the prior policy exactly. Relogin returned to the same conversation with complete saved history. User permissions/business records were unchanged.

Client tests were added to Web CI, `scripts/verify.sh web`, and image builds; anonymous checks entered `scripts/verify-gateway.py`. That run did not execute the script's full policy-mutation/replay suite; only the described independent protocol checks were run. This record does not establish complete I07 or E5 acceptance.
