# Operion web

The E2 web client uses assistant-ui over AG-UI. The browser sends requests to
same-origin Next.js routes; only the Next.js server can read the Agent service
credential.

```bash
cp .env.example .env.local
npm ci
npm run dev
```

Use Node.js 22 or newer. The current dependency lock also builds under Node
20.20, but one transitive `nanoid` package declares Node 22 as its supported
minimum.

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
