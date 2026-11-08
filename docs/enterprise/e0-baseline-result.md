# E0 experimental baseline acceptance

Acceptance date: 2026-09-16; run `20260916T205333Z`; verdict `PASSED` for the experimental environment. Historical record, including the explicitly dated subsequent permission/readback updates below. Current status lives in the [index](README.md), not this baseline.

This pass allowed controlled E1 read-only development. It did not complete E1 or enable Operion writes. Detailed/sensitive backup evidence stayed in controlled local `reports/enterprise/e0/20260916T205333Z/`, outside Git.

## Subgoal results

| Goal | Verdict | Evidence |
| --- | --- | --- |
| E0.1 Status | PASS | Twenty 10 WWI Companies, 25 People, 18 Company links; ERPNext core counts 8/2/9/25/8/2 agreed with exports |
| E0.2 Versions/topology | PASS | Twenty 2.39.0; ERPNext 16.34.2/Frappe 16.33.1; PostgreSQL 16.15; MariaDB 11.8.9; SQL Server 16.0.4275.2; SGLang 0.5.19; health probes passed |
| E0.3 Credentials/permission | PASS, narrowed scope | Twenty read key passed reads/negative writes; later ERPNext protected-DocType gate described below |
| E0.4 Recovery | PASS | Twenty database plus 63 storage files, ERPNext database/files, WWI backup restored/checked in isolated temporary targets, then cleaned up |
| E0.5 Demo rules | PASS | `fulfillment-v1`: 2016-05-31, Europe/Berlin, `AI Demo GmbH`, `WWI Main Warehouse`, `Each`→`Unit`, `ship_by`; versioned F01–F06 expectations |
| E0.6 Bypass paths | PASS, then-current scope | Built-in Twenty Helper lacked write/delete/all-tools permissions; no Operion Agent/Worker/credentials yet existed; unauthenticated SGLang denied |

## Verified baseline

- Commit `3ac3d946acb86c38727f8ed8311c7b6ef55f0a83`, with the then-current documentation/status worktree changes.
- WWI raw backup SHA-256: `e842bad6ce02f74f166947e559dab1b476edd7eaae3da2ab9e3f522f1dd87124`.
- Model `RadixArk/Qwen3.8-27B-NVFP4`, revision `554ebba9b5f1b79dc11246341960360e6ef05ef4`; tool-call, strict structured-output, and thinking-disabled probes passed.
- Local `.env` restricted to 0600; no secret values in reports.

## Recorded limits and later gates

1. Existing Twenty `test` key remained Admin and was classified ETL/admin-only, never Agent. On 2026-09-19, `TWENTY_API_KEY_READ_ONLY` read successfully and denied create/update/delete; temporary records were cleaned. It was an E1 read-adapter credential candidate.
2. ERPNext roles are additive. The final 2026-09-19 user retained `Operion Read Only` plus automatic roles. Customer/Supplier/Item/Sales Order/Purchase Order/Warehouse/Bin/UOM read succeeded; protected mutations failed and direct creates returned 403. Contact/ToDo were explicit exceptions, so the credential was not globally read-only. Original E1 permitted only fixed GET clients and two business MCP tools with no arbitrary target arguments.
3. ERPNext custom source keys lacked database uniqueness; order parent DocTypes had redundant child fields. Readback remained usable, but E1 reconciliation/E3 idempotency probes had to handle these limits.
4. Subsequent E1 source-key reconciliation matched ERPNext 72/72 and Twenty 35/35; unexported completed purchases were `not_applicable`.
5. Ports 1433, 3000, 8080, 9443, and 30000 then bound all host interfaces. Service authentication was checked, but firewall rules were inaccessible. Enterprise operation required network verification and narrower model/database exposure.

At this historical gate, no Agent before E2 and no Operion write path before E3/E4. These statements describe release sequencing then, not an assertion that today's Agent/action implementation is absent.
