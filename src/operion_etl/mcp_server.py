from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .read_tools import AccessScope, CanonicalRepository


def create_server(
    repository: CanonicalRepository,
    scope: AccessScope,
) -> MCPServer:
    """Expose exactly the two E1 business tools over MCP."""
    server = MCPServer(
        "operion-read-tools",
        instructions=(
            "Read-only business tools for the caller's server-defined customer "
            "scope. Tool arguments cannot change authorization scope or data sources."
        ),
        version="0.1.0",
    )
    read_only = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )

    @server.tool(
        name="get_customer_overview",
        description=(
            "Return an allowlisted customer, contacts, and recent orders within "
            "the server-defined customer scope. Has no side effects."
        ),
        annotations=read_only,
        structured_output=True,
    )
    def get_customer_overview(
        customer: str,
        max_orders: int = 20,
    ) -> dict[str, Any]:
        return repository.customer_overview(customer, scope, max_orders)

    @server.tool(
        name="check_fulfillment",
        description=(
            "Evaluate one frozen fulfillment case with deterministic quantity and "
            "date rules. Has no side effects."
        ),
        annotations=read_only,
        structured_output=True,
    )
    def check_fulfillment(case_id: str) -> dict[str, Any]:
        return repository.fulfillment_case(case_id)

    return server


def server_from_environment() -> MCPServer:
    canonical_dir = Path(
        os.environ.get(
            "OPERION_CANONICAL_DIR",
            "data/canonical/wwi-v1-small-20260913-v4",
        )
    )
    raw_customer_ids = os.environ.get("OPERION_CUSTOMER_IDS", "")
    customer_ids = frozenset(
        value.strip() for value in raw_customer_ids.split(",") if value.strip()
    )
    if not customer_ids:
        raise RuntimeError(
            "OPERION_CUSTOMER_IDS must define the server-side customer scope"
        )
    identity_value = os.environ.get("OPERION_IDENTITY_MAP", "").strip()
    if not identity_value:
        raise RuntimeError("OPERION_IDENTITY_MAP is required")
    observed_at = os.environ.get("OPERION_OBSERVED_AT", "").strip()
    twenty_observed_at = os.environ.get("OPERION_TWENTY_OBSERVED_AT", "").strip()
    erpnext_observed_at = os.environ.get("OPERION_ERPNEXT_OBSERVED_AT", "").strip()
    if not observed_at and not (twenty_observed_at and erpnext_observed_at):
        raise RuntimeError(
            "set OPERION_OBSERVED_AT or both OPERION_TWENTY_OBSERVED_AT and "
            "OPERION_ERPNEXT_OBSERVED_AT"
        )
    repository = CanonicalRepository(
        canonical_dir,
        identity_map=Path(identity_value),
        observed_at=observed_at or None,
        twenty_observed_at=twenty_observed_at or None,
        erpnext_observed_at=erpnext_observed_at or None,
        max_snapshot_skew_seconds=int(
            os.environ.get("OPERION_MAX_SNAPSHOT_SKEW_SECONDS", "300")
        ),
    )
    scope = AccessScope(
        operating_company=os.environ.get("OPERION_COMPANY", "AI Demo GmbH"),
        customer_ids=customer_ids,
    )
    return create_server(repository, scope)


def main() -> None:
    server_from_environment().run("stdio")
