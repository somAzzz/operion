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
