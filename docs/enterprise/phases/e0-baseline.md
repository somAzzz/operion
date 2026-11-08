# E0: Environment, permission, and recovery baseline

Status: PASSED, experimental environment, 2026-09-16. Owners: system/data and operations; developer assembles evidence. This is historical acceptance, not a new environment certification.

See [E0 summary](../e0-baseline-result.md). Controlled local evidence: `reports/enterprise/e0/20260916T205333Z/`; sensitive backups/configuration are not committed.

## Goal and entry

Establish usable infrastructure and safety boundaries for recoverable, reproducible work. Entry is the existing repository/deployment access. A written plan does not prove deployed permission restrictions.

## Subgoals

| ID | Goal/deliverable | Verification |
| --- | --- | --- |
| E0.1 | Reconcile README, ETL reports, and target readback into implemented/unverified items | Separate Twenty Company/People and ERPNext evidence; code existence is not deployment |
| E0.2 | Versions/topology: business systems, databases, SGLang/model/template/parser, Python/resources | Health probes, reproducible images/revisions, explicit unknowns |
| E0.3 | Distinct human/ETL/read/Worker/admin identities and AI/MCP/plugin entry points | Isolated negative checks at every Agent execution path; query credentials cannot mutate records/metadata except documented exceptions |
| E0.4 | Back up required data, attachments, mappings, configuration independently | Restore to an isolated instance and check records/relations; backup command success alone is insufficient |
| E0.5 | Pin business date, warehouse, units, reservations, company, sample | Business owner checks inputs/expectations for fifteen cases; no full product training required |
| E0.6 | Constrain built-in AI or close unconstrainable paths; restrict write network to executor | Even a model requesting field deletion cannot cause effects; human admin authority is not delegated to Agent accounts |

Record configuration summaries/secret references, never secret values. Negative permission probes use isolated objects, not destructive operations on real fields.

## Capability matrix questions

- Are built-in AI and API-account permissions independent? Can either bypass read-only policy?
- How are record/company/field permissions enforced, and what extra authority does a service account retain?
- What Task fields, relations, notifications, and workflows exist in the installed Twenty version?
- Does the target support native deduplication, unique references, exact lookup, and atomic conditional updates? E3 may resolve unknowns.
- Does the actual model support configured thinking, structured output, tool results, and streaming? E2 performs full compatibility checks.
- What can backups restore, how long does it take, and what is missing?

## Deliverable and exit

Acceptance package `reports/enterprise/e0/<run-id>/`: inventory, permission matrix, restore results, data status, decisions. Every E0.1–E0.6 has a conclusion. Unknown write capabilities may block writes without blocking read-only development; existing unconstrained Agent write paths must close.

## Failure and next step

If permission cannot be narrowed, close the affected AI path. Repair failed restoration before irreversible preparation. Continue to [E1](e1-read-tools.md), updating state under the [acceptance rules](../delivery-plan.md).
