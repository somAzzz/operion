# E2 read-only Agent runbook

## Fixed compatibility set

- SGLang model: `RadixArk/Qwen3.8-27B-NVFP4`, served as `qwen3.8-27b`
- revision: `554ebba9b5f1b79dc11246341960360e6ef05ef4`
- reasoning parser: `qwen3`; tool parser: `qwen3_coder`
- Pydantic AI: 2.46.0; OpenAI SDK: 3.16.2
- FastAPI: 0.141.1; Uvicorn: 0.53.0
- assistant-ui: 0.15.21; react-ag-ui: 0.0.60; AG-UI client: 0.0.59
- Next.js: 16.3.5; React: 19.3.0; Node.js: 22+ recommended

Python and frontend packages are locked by `uv.lock` and
`apps/web/package-lock.json`. Thinking is disabled in normal runs and in the UI;
both thinking modes are covered by the model compatibility probe.

## Start

Start SGLang with the fixed model/revision and these relevant flags:

```bash
sglang serve \
  --model-path RadixArk/Qwen3.8-27B-NVFP4 \
  --revision 554ebba9b5f1b79dc11246341960360e6ef05ef4 \
  --port 30000 --api-key dummy --served-model-name qwen3.8-27b \
  --reasoning-parser qwen3 --tool-call-parser qwen3_coder \
  --max-running-requests 4
```

Install dependencies and configure the Agent without reusing administrator or
business-write credentials:

```bash
uv sync --extra dev
export OPERION_AGENT_TOKEN='<random-local-service-token>'
export OPERION_IDENTITY_MAP='reports/enterprise/e2/20260919T-preseed/identity_map.reconciled.csv'
export OPERION_OBSERVED_AT='<fresh-ISO-8601-observation-time>'
export OPERION_CUSTOMER_IDS='operion:e2:organization:customer:ambiguous-a,operion:e2:organization:customer:ambiguous-b'
uv run operion-agent
```

In another shell:

```bash
cd apps/web
cp .env.example .env.local
# Set the same OPERION_AGENT_TOKEN in .env.local.
npm ci
npm run dev
```

The UI is at `http://localhost:3000`. The browser calls same-origin proxy routes;
the Agent credential must never use a `NEXT_PUBLIC_` name.

## Verify

```bash
uv run ruff format --check .
uv run ruff check .
PYDANTIC_AI_NO_BANNER=1 uv run python -m unittest discover -s tests -q
cd apps/web && npm run build
```

Run model compatibility and the 15 cases three times:

```bash
uv run operion-model-compatibility \
  --identity-map "$OPERION_IDENTITY_MAP" \
  --observed-at "$OPERION_OBSERVED_AT" \
  --output reports/enterprise/e2/<run>/model-compatibility.json

uv run operion-evaluate-e2 \
  --identity-map "$OPERION_IDENTITY_MAP" \
  --observed-at "$OPERION_OBSERVED_AT" \
  --output reports/enterprise/e2/<run>/agent-evaluation.json
```

Acceptance requires all seven compatibility probes and all 45 case runs to
pass. The report intentionally excludes the model API key and Agent token.

## Recovery and limits

- Delete only the local `var/operion-agent.sqlite3` file to reset demo history;
  this is not a business-system delete.
- SQLite locking is process-local, so E2 runs one Uvicorn worker. Multi-worker
  operation requires a shared lock and session store.
- A source outage returns `source_unavailable`; a stale satisfiable result is
  downgraded to `insufficient_information`; neither is reported as no orders or
  a delivery guarantee.
- E2 has no write tool, approval endpoint, or business-write credential. Those
  remain E3 work.
