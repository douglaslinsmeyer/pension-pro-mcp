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
from pension_pro_mcp.tools.projects import (
    search_projects, get_project_details, complete_task,
    uncomplete_task, reassign_task, create_project_from_template,
)


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


@mcp.tool()
async def search_projects_tool(
    ctx: Context[ServerSession, AppContext],
    status: str | None = None,
    project_type: str | None = None,
    plan_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search and filter projects by status, type, or plan."""
    client = ctx.request_context.lifespan_context.client
    return await search_projects(client, status=status, project_type=project_type, plan_id=plan_id, limit=limit)


@mcp.tool()
async def get_project_details_tool(
    ctx: Context[ServerSession, AppContext],
    project_id: int,
) -> dict:
    """Get a project with its task groups, tasks, participants, and notes."""
    client = ctx.request_context.lifespan_context.client
    return await get_project_details(client, project_id=project_id)


@mcp.tool()
async def complete_task_tool(
    ctx: Context[ServerSession, AppContext],
    task_id: int,
) -> dict:
    """Mark a task as complete."""
    client = ctx.request_context.lifespan_context.client
    result = await complete_task(client, task_id=task_id)
    return {"success": True, "task_id": task_id, "result": result}


@mcp.tool()
async def uncomplete_task_tool(
    ctx: Context[ServerSession, AppContext],
    task_id: int,
) -> dict:
    """Undo task completion — revert a task to incomplete."""
    client = ctx.request_context.lifespan_context.client
    result = await uncomplete_task(client, task_id=task_id)
    return {"success": True, "task_id": task_id, "result": result}


@mcp.tool()
async def reassign_task_tool(
    ctx: Context[ServerSession, AppContext],
    task_id: int,
    assigned_to_id: int,
) -> dict:
    """Reassign a task to a different employee."""
    client = ctx.request_context.lifespan_context.client
    result = await reassign_task(client, task_id=task_id, assigned_to_id=assigned_to_id)
    return {"success": True, "task_id": task_id, "assigned_to_id": assigned_to_id, "result": result}


@mcp.tool()
async def create_project_from_template_tool(
    ctx: Context[ServerSession, AppContext],
    plan_id: int,
    template_id: int,
) -> dict:
    """Create a new project on a plan from a project template."""
    client = ctx.request_context.lifespan_context.client
    return await create_project_from_template(client, plan_id=plan_id, template_id=template_id)


def main() -> None:
    """CLI entry point."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
