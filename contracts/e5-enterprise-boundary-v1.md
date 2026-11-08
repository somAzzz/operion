# E5 enterprise-boundary contract v1

Status: Technical controls implemented; single-user read-only pilot incomplete. Mark that scope complete only after `operion-evaluate-e5` returns `passed` for actual-environment v2 evidence. Multiple-user enterprise operation and real writes need separate acceptance.

## Identity and authority

- Enterprise mode accepts only asymmetrically signed OIDC bearer tokens with allowed issuer, audience, and algorithm; require `exp`, `iat`, `sub`, and revocable `sid`/`jti`.
- JWT proves authentication, not Operion authority. Resolve tenant, single Company, canonical customer scope, and roles from server identity policy on every request.
- Reload changed policy by file version. Disabled users, revoked sessions, or increased `valid_after` block old tokens.
- Roles are only `agent_read`, `followup_proposer`, `action_reader`, `action_approver`, and `action_operator`; reject unknown roles.
- Conversation owner keys include tenant and stable user ID. Deny cross-user/tenant history, cancellation, and action queries.

## Browser and service boundaries

Trusted ingress performs OIDC login and stores access/refresh tokens in server sessions. Browser holds only an opaque Secure/HttpOnly/SameSite session cookie. Strip client authentication/forwarding headers and inject session-derived `x-forwarded-access-token`. Next.js reads/forwards it only server-side, accepts no browser token cookie or enterprise static-token fallback, and never creates a `NEXT_PUBLIC_*` token. Next.js must be reachable only through trusted ingress.

Next.js checks current identity policy through `/api/identity` and checks functional roles on each protected request; backend independently validates JWT/authority. Non-read browser requests require same-origin Origin; sign-out is same-origin POST, deletes server session, and terminates IdP session. Already-running requests keep their timeout; logout does not claim to revoke in-flight work automatically. Public GET/HEAD login/build assets contain no identity or business data; business pages/APIs remain protected. See the [gateway runbook](../ops/auth-gateway.md), [session recovery](../docs/enterprise/session-expiry-login.md), and [navigation access](../docs/enterprise/navigation-access.md).

Agent and Action API independently validate tokens. Agent derives scope/tools from identity. Action approval also requires the server CSRF secret. Generic proposals/revisions cannot bypass server-owned E4 fact resolution.

## Write release lock

Enterprise default `OPERION_WRITES_ENABLED=0` rejects approval, disables follow-up proposals, and prevents Worker startup. Opening the one E4 write path requires all of:

- `OPERION_WRITES_ENABLED=1`
- Nonempty `OPERION_RELEASE_ID`
- Applicable O01–O08 and E4 regressions passed
- Current operating hours, on-call coverage, backup, and rollback confirmed

New tools/actions remain default-deny.

## Audit, retention, and monitoring

- Agent access events are append-only; SQLite triggers forbid update/delete.
- Raw conversation/tool content defaults to at most 24 hours. `operion-session-purge` clears content while preserving run metadata/access events.
- Action events retain per-action hash chains. `/api/operations` is `action_operator` only and reports state counts, oldest UNKNOWN, expired leases, pauses, and Worker heartbeat.
- Heartbeat contains Worker state, current action, and release. External monitoring must actually deliver UNKNOWN > five minutes, stalled Worker, expired lease, audit anomaly, backup beyond RPO, and disk alerts. Unattended writes remain paused.

## Completion criteria

Code tests/local fault injection cannot replace actual use. Local deployment may qualify; simulated observation traffic does not. Submit strict v2 evidence identifying public-sample or approved private data and one actual user's identity/revocation, secret rotation, network isolation, personally received alerts, encrypted off-host backup/isolated restore, measured RPO/RTO, automated five-session capacity, rollback, deletion, closed write entry points, and at least ten business days of nonzero legitimate traffic. The actual operator self-signs. Controlled cross-scope test identities do not count as real users. Single-user acceptance enables neither M4 writes nor private-data use outside the evidenced scope.
