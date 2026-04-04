"""PensionPro MCP Server entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.plans import search_plans, get_plan_details, get_plan_projects
from pension_pro_mcp.tools.projects import (
    search_projects, get_project_details, complete_task,
    uncomplete_task, reassign_task, create_project_from_template,
)
from pension_pro_mcp.tools.clients import search_clients, get_client_details, search_contacts
from pension_pro_mcp.tools.todos import search_todos, get_todo, create_todo, update_todo
from pension_pro_mcp.tools.notes import add_note, get_notes


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


@mcp.tool()
async def search_clients_tool(
    ctx: Context[ServerSession, AppContext],
    name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search and filter clients by company name."""
    client = ctx.request_context.lifespan_context.client
    return await search_clients(client, name=name, limit=limit)


@mcp.tool()
async def get_client_details_tool(
    ctx: Context[ServerSession, AppContext],
    client_id: int,
) -> dict:
    """Get a client with their plans and notes."""
    client = ctx.request_context.lifespan_context.client
    return await get_client_details(client, client_id=client_id)


@mcp.tool()
async def search_contacts_tool(
    ctx: Context[ServerSession, AppContext],
    name: str | None = None,
    client_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search and filter contacts by name or client."""
    client = ctx.request_context.lifespan_context.client
    return await search_contacts(client, name=name, client_id=client_id, limit=limit)


@mcp.tool()
async def search_todos_tool(
    ctx: Context[ServerSession, AppContext],
    status: str | None = None,
    priority: str | None = None,
    plan_id: int | None = None,
    project_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search and filter to-dos by status, priority, plan, or project."""
    client = ctx.request_context.lifespan_context.client
    return await search_todos(client, status=status, priority=priority, plan_id=plan_id, project_id=project_id, limit=limit)


@mcp.tool()
async def get_todo_tool(
    ctx: Context[ServerSession, AppContext],
    todo_id: int,
) -> dict:
    """Get a to-do with its comments."""
    client = ctx.request_context.lifespan_context.client
    return await get_todo(client, todo_id=todo_id)


@mcp.tool()
async def create_todo_tool(
    ctx: Context[ServerSession, AppContext],
    subject: str,
    description: str | None = None,
    priority_id: int | None = None,
    due_date: str | None = None,
    status_id: int | None = None,
    assigned_to_contact_id: int | None = None,
    plan_id: int | None = None,
    project_id: int | None = None,
    contact_id: int | None = None,
) -> dict:
    """Create a new to-do, optionally linked to a plan, project, or contact."""
    client = ctx.request_context.lifespan_context.client
    return await create_todo(
        client, subject=subject, description=description, priority_id=priority_id,
        due_date=due_date, status_id=status_id, assigned_to_contact_id=assigned_to_contact_id,
        plan_id=plan_id, project_id=project_id, contact_id=contact_id,
    )


@mcp.tool()
async def update_todo_tool(
    ctx: Context[ServerSession, AppContext],
    todo_id: int,
    subject: str | None = None,
    description: str | None = None,
    status_id: int | None = None,
    priority_id: int | None = None,
    due_date: str | None = None,
) -> dict:
    """Update an existing to-do's subject, description, status, priority, or due date."""
    client = ctx.request_context.lifespan_context.client
    return await update_todo(client, todo_id=todo_id, subject=subject, description=description, status_id=status_id, priority_id=priority_id, due_date=due_date)


@mcp.tool()
async def add_note_tool(
    ctx: Context[ServerSession, AppContext],
    text: str,
    plan_id: int | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
    contact_id: int | None = None,
    category_id: int | None = None,
) -> dict:
    """Add a note to a plan, project, task, or contact. At least one entity ID must be provided."""
    client = ctx.request_context.lifespan_context.client
    return await add_note(client, text=text, plan_id=plan_id, project_id=project_id, task_id=task_id, contact_id=contact_id, category_id=category_id)


@mcp.tool()
async def get_notes_tool(
    ctx: Context[ServerSession, AppContext],
    plan_id: int | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
    contact_id: int | None = None,
    limit: int = 25,
) -> list[dict]:
    """Get notes for an entity (plan, project, task, or contact). At least one entity ID must be provided."""
    client = ctx.request_context.lifespan_context.client
    return await get_notes(client, plan_id=plan_id, project_id=project_id, task_id=task_id, contact_id=contact_id, limit=limit)


def main() -> None:
    """CLI entry point."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
