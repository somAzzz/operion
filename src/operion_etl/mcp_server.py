from __future__ import annotations

from typing import Any, Literal

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .agent_runtime import repository_from_environment, scope_from_environment
from .read_tools import AccessScope, CanonicalRepository


def create_server(
    repository: CanonicalRepository,
    scope: AccessScope,
) -> MCPServer:
    """Expose the shared, read-only business query service over MCP."""
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
        name="get_customer_portfolio_summary",
        description=(
            "Count and summarize customers within the server-defined customer "
            "scope. Has no side effects."
        ),
        annotations=read_only,
        structured_output=True,
    )
    def get_customer_portfolio_summary(customer: Literal["*"] = "*") -> dict[str, Any]:
        return repository.customer_portfolio_summary(scope)

    @server.tool(annotations=read_only, structured_output=True)
    def search_customers(
        query: str = "", limit: int = 10, cursor: str | None = None
    ) -> dict[str, Any]:
        """Search or list authorized customers; partial names are supported."""
        return repository.search_customers(query, scope, limit, cursor)

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

    @server.tool(annotations=read_only, structured_output=True)
    def list_sales_orders(
        customer_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        limit: int = 10,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List authorized sales orders with validated customer/date/status filters."""
        return repository.list_sales_orders(
            scope, customer_id, date_from, date_to, status, limit, cursor
        )

    @server.tool(annotations=read_only, structured_output=True)
    def get_sales_order(order_id: str) -> dict[str, Any]:
        """Return one authorized sales order and its item lines."""
        return repository.get_sales_order(order_id, scope)

    @server.tool(annotations=read_only, structured_output=True)
    def search_suppliers(
        query: str = "", limit: int = 10, cursor: str | None = None
    ) -> dict[str, Any]:
        """Search or list authorized suppliers; partial names are supported."""
        return repository.search_suppliers(query, scope, limit, cursor)

    @server.tool(annotations=read_only, structured_output=True)
    def get_supplier_overview(supplier_id: str, max_orders: int = 20) -> dict[str, Any]:
        """Return an authorized supplier, contacts, and recent purchase orders."""
        return repository.supplier_overview(supplier_id, scope, max_orders)

    @server.tool(annotations=read_only, structured_output=True)
    def list_purchase_orders(
        supplier_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
        limit: int = 10,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List authorized purchase orders with supplier/date/status filters."""
        return repository.list_purchase_orders(
            scope, supplier_id, date_from, date_to, status, limit, cursor
        )

    @server.tool(annotations=read_only, structured_output=True)
    def get_purchase_order(order_id: str) -> dict[str, Any]:
        """Return one authorized purchase order and its item lines."""
        return repository.get_purchase_order(order_id, scope)

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
    return create_server(repository_from_environment(), scope_from_environment())


def main() -> None:
    server_from_environment().run("stdio")
