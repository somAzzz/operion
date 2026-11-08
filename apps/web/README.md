# Operion web

The E2 web client uses assistant-ui over AG-UI. The browser sends requests to
same-origin Next.js routes; only the Next.js server can read the Agent service
credential.

```bash
cp .env.example .env.local
npm ci
npm run dev
```

Use Node.js 22.18 or newer for the implemented session/navigation checks and
current CI/deployment baseline. A historical build passed under Node 20.20 with
engine warnings (including the transitive `nanoid` minimum); that does not establish support for today's complete Web checks.
Run `scripts/verify.sh web` from the repository root for session/navigation tests,
TypeScript, the webpack production build, and server-rendered access checks.

The active conversation ID is kept in local storage. Message history and tool
authorization remain authoritative in the Python service.

For enterprise authentication, use the [local HTTPS/OIDC gateway](../../ops/auth-gateway.md).
The gateway issues an opaque browser session and forwards tokens only on the
private network. Next.js checks the current backend identity policy and route
roles on every request; browser token cookies and static service-token fallback
are disabled in enterprise mode. Set `OPERION_PUBLIC_ORIGIN` to the exact HTTPS
origin. The deployment must keep Next.js and the Python APIs private.

`/session` provides a same-origin POST sign-out. Container builds use the
standalone output; local `npm run dev` and `npm run start` remain supported.
