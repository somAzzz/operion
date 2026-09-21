# Operion

English | [中文](README.zh-CN.md)

Operion is a controlled business agent layer built on top of Twenty CRM and
ERPNext. Agent and MCP workflows are the product focus; the business systems and a
lightweight ETL pipeline provide governed facts and tools.

The goal is to keep material business judgment with people while agents help with
search, consolidation, recommendations, and narrowly controlled execution.

![Operion system architecture](docs/imgs/pipeline.png)

## Current status

E0 through E4 have passed. The
project currently includes:

- a reproducible Wide World Importers download and minimal ETL pipeline;
- canonical records and target mappings for Twenty and ERPNext;
- pre-import validation for the generated files;
- Twenty REST readback for 10 WWI Companies and 25 People, including the 18
  expected Company relations;
- an ERPNext API audit covering 8 Customers, 2 Suppliers, 9 Items, 25 Contacts,
  8 Sales Orders, and 2 Purchase Orders;
- a GET-only cross-system identity reconciliation with 72/72 ERPNext and 35/35
  Twenty target identities matched;
- deterministic customer, supplier, sales-order, purchase-order, portfolio, and
  fulfilment services exposed as exactly ten read-only MCP tools;
- a Pydantic AI / local SGLang read-only Agent with trusted server-side history,
  an AG-UI FastAPI endpoint, and an assistant-ui evidence desk;
- a PostgreSQL-backed action control service with immutable revisions and
  decisions, trusted approval, leases, reconciliation, and an idempotent E3
  fault-injection stub;
- approval and action-status pages backed by the server-side action ledger; and
- one separately approved Twenty internal follow-up Task path with deterministic
  IDs, exact readback, and recovery after response loss or worker crashes.

The E2 baseline passes all 15 behavior cases three times and all seven model
compatibility probes. E3 passes W01-W15 against a persistent stub, and E4
repeats the applicable gates against Twenty 2.39.0. Writes remain limited to one
internal Task in the isolated public/simulated demo workspace; E5 enterprise
identity, real-data controls, monitoring, and release operations are not yet
approved.

The interview demonstration adds scoped customer/supplier search and order
listing/detail. It includes both a separate simulated dataset and a pinned,
deterministically extracted WWI public-sample dataset at the same demonstration
scale, while retaining the deterministic fulfilment check and its 15 fixed
evaluation cases. The first agent-initiated
write is deliberately limited to creating one internal follow-up task after an
exact preview and human approval.

Delivery sequence:

```text
use cases and expected answers
  → small linked dataset
  → read-only adapters
  → business tools and MCP
  → agent and evaluations
  → one controlled write
  → synchronization when justified
```

## Documentation

The detailed design documents are currently written in Chinese:

- [Enterprise operating plan and staged subplans](docs/enterprise/README.md)
- [Agent and MCP boundaries](docs/agent-boundaries.md)
- [Minimum demonstration and evaluations](docs/minimum-demo.md)
- [Human functions and agent design map](docs/human-functions-agent-map.md)
- [Data directory conventions](data/README.md)
- [WWI download and ETL runbook](ops/data-pipeline.md)
- [Canonical data contract](contracts/canonical-v1.md)
- [E2 read-only Agent runbook](ops/e2-agent.md)
- [Interview demo data runbook](ops/interview-demo-data.md)
- [WWI interview dataset runbook](ops/interview-wwi-data.md)
- [Interview demo questions and expected answers](docs/interview-demo.md)
- [WWI interview questions and expected answers](docs/interview-wwi.md)
- [Current data/scope diagnostic](docs/interview-demo-diagnostic.md)
- [E3 action-control contract](contracts/e3-action-control-v1.md)
- [E3 action-control runbook](ops/e3-action-control.md)
- [E4 follow-up Task contract](contracts/e4-followup-task-v1.md)
- [E4 follow-up Task runbook](ops/e4-followup-task.md)
- [E5 enterprise boundary](contracts/e5-enterprise-boundary-v1.md)
- [E5 enterprise pilot runbook](ops/e5-enterprise-pilot.md)

## Repository layout

```text
operion/
├── src/operion_etl/          # Reproducible extraction, mapping, validation, and audits
├── tests/                    # Deterministic ETL and validation tests
├── contracts/                # Canonical data and future tool contracts
├── mappings/                 # Source-to-target mappings and fixed assumptions
├── docs/                     # Product, safety, evaluation, and operating plans
├── ops/                      # Runbooks for data preparation and recovery
├── evaluations/              # Evaluation definitions and fixtures
├── data/                     # Local source snapshots and generated exports
└── reports/                  # Local validation and reconciliation evidence
```

Business data and generated reports are excluded from version control by default.

## ETL quick start

Requirements: Python 3.11+, Docker, and the source/target systems described in the
[runbook](ops/data-pipeline.md).

```bash
PYTHONPATH=src python3 -m operion_etl download-wwi
scripts/restore_wwi.sh data/raw/wwi/<snapshot>/WideWorldImporters-Full.bak
PYTHONPATH=src python3 -m operion_etl run \
  --snapshot data/raw/wwi/<snapshot> \
  --batch-id <unique-batch-id>
```

Run the deterministic test suite with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

See the [runbook](ops/data-pipeline.md) for pre-import validation, Twenty loading,
ERPNext import prerequisites, and post-import reconciliation.
