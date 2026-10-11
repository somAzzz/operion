# Offline test fixtures

wwi-small is the 2026-09-13 v4 public WWI sample already used by the read, MCP, and Agent tests. The 2026-09-19 E1 input CSVs are byte-identical to this batch. wwi-small-identity.csv preserves the E1 mapping shape for E2 batch preparation but replaces all target IDs with deterministic synthetic identifiers. companies-template-header.csv preserves only the header from the public Twenty import template sample.

These files are checked in so offline tests do not depend on an operator's ignored data or reports history. They are test inputs, not a live business source.
