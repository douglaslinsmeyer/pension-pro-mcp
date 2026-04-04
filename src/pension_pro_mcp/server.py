"""PensionPro MCP Server entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.plans import search_plans, get_plan_details, get_plan_projects
from pension_pro_mcp.tools.projects import (
    search_projects, get_project_details, get_task_group, get_task_details, complete_task,
    uncomplete_task, reassign_task, create_project_from_template,
)
from pension_pro_mcp.tools.clients import search_clients, get_client_details, search_contacts
from pension_pro_mcp.tools.todos import search_todos, get_todo, create_todo, update_todo
from pension_pro_mcp.tools.notes import add_note, get_notes
from pension_pro_mcp.tools.worktrays import get_worktrays, get_worktray


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


# --- Plan tools ---


@mcp.tool(name="search_plans")
async def _search_plans(
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


@mcp.tool(name="get_plan_details")
async def _get_plan_details(
    ctx: Context[ServerSession, AppContext],
    plan_id: int,
) -> dict:
    """Get comprehensive details for a single plan.

    Returns the plan record with contacts, cycles, services, investments, and fee schedules.
    """
    client = ctx.request_context.lifespan_context.client
    return await get_plan_details(client, plan_id=plan_id)


@mcp.tool(name="get_plan_projects")
async def _get_plan_projects(
    ctx: Context[ServerSession, AppContext],
    plan_id: int,
    status: str | None = None,
) -> list[dict]:
    """Get all projects for a plan with task completion summaries.

    Each project includes a task_summary with total, completed, and pending counts.
    """
    client = ctx.request_context.lifespan_context.client
    return await get_plan_projects(client, plan_id=plan_id, status=status)


# --- Project & task tools ---


@mcp.tool(name="search_projects")
async def _search_projects(
    ctx: Context[ServerSession, AppContext],
    status: str | None = None,
    project_type: str | None = None,
    plan_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search and filter projects by status, type, or plan."""
    client = ctx.request_context.lifespan_context.client
    return await search_projects(client, status=status, project_type=project_type, plan_id=plan_id, limit=limit)


@mcp.tool(name="get_project_details")
async def _get_project_details(
    ctx: Context[ServerSession, AppContext],
    project_id: int,
) -> dict:
    """Get a project with its task groups, tasks, participants, and notes."""
    client = ctx.request_context.lifespan_context.client
    return await get_project_details(client, project_id=project_id)


@mcp.tool(name="get_task_group")
async def _get_task_group(
    ctx: Context[ServerSession, AppContext],
    task_group_id: int,
) -> dict:
    """Get a task group with all its tasks."""
    client = ctx.request_context.lifespan_context.client
    return await get_task_group(client, task_group_id=task_group_id)


@mcp.tool(name="get_task_details")
async def _get_task_details(
    ctx: Context[ServerSession, AppContext],
    task_id: int,
) -> dict:
    """Get a single task with its current state, assignment, and notes."""
    client = ctx.request_context.lifespan_context.client
    return await get_task_details(client, task_id=task_id)


@mcp.tool(name="complete_task")
async def _complete_task(
    ctx: Context[ServerSession, AppContext],
    task_id: int,
) -> dict:
    """Mark a task as complete."""
    client = ctx.request_context.lifespan_context.client
    result = await complete_task(client, task_id=task_id)
    return {"success": True, "task_id": task_id, "result": result}


@mcp.tool(name="uncomplete_task")
async def _uncomplete_task(
    ctx: Context[ServerSession, AppContext],
    task_id: int,
) -> dict:
    """Undo task completion — revert a task to incomplete."""
    client = ctx.request_context.lifespan_context.client
    result = await uncomplete_task(client, task_id=task_id)
    return {"success": True, "task_id": task_id, "result": result}


@mcp.tool(name="reassign_task")
async def _reassign_task(
    ctx: Context[ServerSession, AppContext],
    task_id: int,
    assigned_to_id: int,
) -> dict:
    """Reassign a task to a different employee."""
    client = ctx.request_context.lifespan_context.client
    result = await reassign_task(client, task_id=task_id, assigned_to_id=assigned_to_id)
    return {"success": True, "task_id": task_id, "assigned_to_id": assigned_to_id, "result": result}


@mcp.tool(name="create_project_from_template")
async def _create_project_from_template(
    ctx: Context[ServerSession, AppContext],
    plan_id: int,
    template_id: int,
) -> dict:
    """Create a new project on a plan from a project template."""
    client = ctx.request_context.lifespan_context.client
    return await create_project_from_template(client, plan_id=plan_id, template_id=template_id)


# --- Client & contact tools ---


@mcp.tool(name="search_clients")
async def _search_clients(
    ctx: Context[ServerSession, AppContext],
    name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search and filter clients by company name."""
    client = ctx.request_context.lifespan_context.client
    return await search_clients(client, name=name, limit=limit)


@mcp.tool(name="get_client_details")
async def _get_client_details(
    ctx: Context[ServerSession, AppContext],
    client_id: int,
) -> dict:
    """Get a client with their plans and notes."""
    client = ctx.request_context.lifespan_context.client
    return await get_client_details(client, client_id=client_id)


@mcp.tool(name="search_contacts")
async def _search_contacts(
    ctx: Context[ServerSession, AppContext],
    name: str | None = None,
    client_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search and filter contacts by name or client."""
    client = ctx.request_context.lifespan_context.client
    return await search_contacts(client, name=name, client_id=client_id, limit=limit)


# --- To-do tools ---


@mcp.tool(name="search_todos")
async def _search_todos(
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


@mcp.tool(name="get_todo")
async def _get_todo(
    ctx: Context[ServerSession, AppContext],
    todo_id: int,
) -> dict:
    """Get a to-do with its comments."""
    client = ctx.request_context.lifespan_context.client
    return await get_todo(client, todo_id=todo_id)


@mcp.tool(name="create_todo")
async def _create_todo(
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


@mcp.tool(name="update_todo")
async def _update_todo(
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


# --- Notes tools ---


@mcp.tool(name="add_note")
async def _add_note(
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


@mcp.tool(name="get_notes")
async def _get_notes(
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


# --- Worktray tools ---


@mcp.tool(name="get_worktrays")
async def _get_worktrays(
    ctx: Context[ServerSession, AppContext],
    active_only: bool = True,
    limit: int = 100,
) -> list[dict]:
    """List all worktrays. Set active_only=false to include inactive worktrays."""
    client = ctx.request_context.lifespan_context.client
    return await get_worktrays(client, active_only=active_only, limit=limit)


@mcp.tool(name="get_worktray")
async def _get_worktray(
    ctx: Context[ServerSession, AppContext],
    worktray_id: int,
) -> dict:
    """Get a worktray with its members and all active (incomplete) tasks routed to it."""
    client = ctx.request_context.lifespan_context.client
    return await get_worktray(client, worktray_id=worktray_id)


def main() -> None:
    """CLI entry point."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
