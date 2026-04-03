"""PensionPro MCP Server entry point."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from pension_pro_mcp.client import PensionProClient


@dataclass
class AppContext:
    """Shared application context available to all tools."""

    client: PensionProClient


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage the PensionPro HTTP client lifecycle."""
    client = PensionProClient()
    try:
        yield AppContext(client=client)
    finally:
        await client.close()


mcp = FastMCP(
    "PensionPro",
    lifespan=app_lifespan,
)

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from pension_pro_mcp.tools.plans import search_plans, get_plan_details, get_plan_projects


@mcp.tool()
async def search_plans_tool(
    ctx: Context[ServerSession, AppContext],
    name: str | None = None,
    status: str | None = None,
    plan_type: str | None = None,
    client_name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search and filter pension plans by name, status, type, or client.

    Returns a summary list of matching plans.
    """
    client = ctx.request_context.lifespan_context.client
    return await search_plans(client, name=name, status=status, plan_type=plan_type, client_name=client_name, limit=limit)


@mcp.tool()
async def get_plan_details_tool(
    ctx: Context[ServerSession, AppContext],
    plan_id: int,
) -> dict:
    """Get comprehensive details for a single plan.

    Returns the plan record with contacts, cycles, services, investments, and fee schedules.
    """
    client = ctx.request_context.lifespan_context.client
    return await get_plan_details(client, plan_id=plan_id)


@mcp.tool()
async def get_plan_projects_tool(
    ctx: Context[ServerSession, AppContext],
    plan_id: int,
    status: str | None = None,
) -> list[dict]:
    """Get all projects for a plan with task completion summaries.

    Each project includes a task_summary with total, completed, and pending counts.
    """
    client = ctx.request_context.lifespan_context.client
    return await get_plan_projects(client, plan_id=plan_id, status=status)


def main() -> None:
    """CLI entry point."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
