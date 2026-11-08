# OpenTelemetry and Langfuse staged acceptance

Date: 2026-10-11. Historical scope: optional tracing, Collector export, Agent/action correlation, synthetic E2 experiments/scores. Not E5 release. Later changes are in [2026-10-17 development telemetry](telemetry-development-acceptance-2026-10-17.md), [dependency fixes](fixes-2026-10-17.md), and [structured answers](structured-answer-evidence.md). Do not treat the health-noise/dependency gaps below as today's unimplemented queue.

| Step | Recorded evidence | Result |
| --- | --- | --- |
| 1 Dependencies/images | `uv sync --frozen --extra dev --extra observability`; `docker compose -f deploy/gateway/compose.yaml build agent web` | PASS |
| 2 Web→Agent | Production Next proxy forwarded valid traceparent without baggage; FastAPI remote-parent tests | PASS |
| 3 Agent/data | Actual `FunctionModel` HTTP/SSE: 13 spans to debug Collector, matching stored run trace/span; timeout terminal state; no prompt content | PASS |
| 4 Approval/Worker | Isolated PostgreSQL 24/24, Worker links to persisted approval; UNKNOWN/idempotency/recovery intact | PASS |
| 5 Collector | Pinned config validation; mock Langfuse `/api/public/otel/v1/traces`, Basic Auth, and ingestion version `4` | PASS |
| 6 Experiment | One actual local-model synthetic case; mock score `traceId`/`observationId` match; `BOOLEAN` numeric `1` | PASS |
| 7 Regression | Python 196 including 24 offline skips; PostgreSQL 24/24; Web TypeScript/build; `git diff --check` and Ruff | PASS within stated split |
| 8 Repeated model | Fifteen cases × three = 45/45; `reports/enterprise/observability/20261011/e2-final.json` | PASS |
| 9 Actual cloud | Content-free parent/child exported/read back as two observations with correct ancestry/auth | PASS |
| 10 Actual E2 cloud | C01 1/1; trace `e34a130fd67ff0be87c94904c53ac679` had 8 nodes including EVALUATOR/AGENT/TOOL/two GENERATION; `operion_correctness=true` bound to the root observation; experiment `316017efe18d4285859b1a168b3c4d90` queryable | PASS |
| 11 Actual UI | [Trace](https://cloud.langfuse.com/project/cmv41jt6h05egad0el9rcy2kh/traces/e34a130fd67ff0be87c94904c53ac679) showed tree/tokens/root score; [experiment](https://cloud.langfuse.com/project/cmv41jt6h05egad0el9rcy2kh/experiments/results?baseline=316017efe18d4285859b1a168b3c4d90) had one item and 100% true correctness | PASS |

Initial grading false positives and an unavailable-source test-adapter omission were repaired with counterexamples before final 45/45. Raw answers/evidence remained in ignored local reports.

Actual OTLP/query/UI through `collector-langfuse.yaml` used configured cloud credentials without publishing them. Synthetic report: `reports/enterprise/observability/20261011/e2-langfuse-live.json`. Collector/Web/Agent were then running/healthy with `OPERION_OTEL_ENABLED=1`. Web's three-second health probes then produced `GET`, `middleware GET`, and `start response` observations; later suppression is documented separately. This run did not originate an authenticated Operion-browser business request; local propagation tests did not establish that full real browser/cloud path. Gateway clicks and long observation were separate acceptance.

The then-current `npm audit --omit=dev` reported three findings: Next.js critical, sharp/source-map-js high; lock pinned Next.js 16.3.5. Tracing work did not upgrade them, so build/functional passes were not security-audit passes. The later 2026-10-17 zero-finding audit is a separate dated record, not a modification of this result.
