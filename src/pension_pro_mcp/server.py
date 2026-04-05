"""PensionPro MCP Server entry point."""

import json
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.pipeline import build_default_pipeline
from pension_pro_mcp.tools.plans import search_plans, get_plan_details, get_plan_projects
from pension_pro_mcp.tools.projects import (
    search_projects, get_project_details, get_task_group, get_task_details, complete_task,
    uncomplete_task, reassign_task, create_project_from_template,
)
from pension_pro_mcp.tools.clients import search_clients, get_client_details, search_contacts
from pension_pro_mcp.tools.todos import search_todos, get_todo, create_todo, update_todo
from pension_pro_mcp.tools.notes import add_note, get_notes
from pension_pro_mcp.tools.worktrays import (
    get_worktrays, get_worktray, get_worktray_member_stats, read_cached_stats,
    get_employee_stats, read_cached_employee_stats,
)
from pension_pro_mcp.tools.swagger import (
    SWAGGER_URL, search_paths, get_endpoint, search_schemas, get_schema,
)
from pension_pro_mcp.tools.help import search_help, get_help_article, list_help_sections

pipeline = build_default_pipeline()


@dataclass
class AppContext:
    """Shared application context available to all tools."""

    client: PensionProClient
    swagger_spec: dict[str, Any] = field(default_factory=dict)


def _cache_dir() -> Path:
    """Return the platform-appropriate cache directory."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "pension-pro-mcp"


SWAGGER_CACHE_DIR = _cache_dir()
SWAGGER_CACHE_FILE = SWAGGER_CACHE_DIR / "swagger.json"
SWAGGER_CACHE_MAX_AGE = 86400  # 24 hours


def _filter_v2(spec: dict[str, Any]) -> dict[str, Any]:
    """Filter spec to v2 endpoints only."""
    spec["paths"] = {p: v for p, v in spec["paths"].items() if p.startswith("/v2/")}
    return spec


def _read_cache() -> dict[str, Any] | None:
    """Read cached swagger spec if it exists and is fresh."""
    if not SWAGGER_CACHE_FILE.exists():
        return None
    age = time.time() - SWAGGER_CACHE_FILE.stat().st_mtime
    if age > SWAGGER_CACHE_MAX_AGE:
        return None
    return _filter_v2(json.loads(SWAGGER_CACHE_FILE.read_text()))


def _write_cache(spec: dict[str, Any]) -> None:
    """Write swagger spec to disk cache."""
    SWAGGER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SWAGGER_CACHE_FILE.write_text(json.dumps(spec))


async def _fetch_swagger_spec() -> dict[str, Any]:
    """Load swagger spec from cache or download fresh."""
    cached = _read_cache()
    if cached is not None:
        return cached

    async with httpx.AsyncClient(timeout=30.0) as http:
        response = await http.get(SWAGGER_URL)
        response.raise_for_status()
        spec = response.json()

    _write_cache(spec)
    return _filter_v2(spec)


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage the PensionPro HTTP client lifecycle."""
    client = PensionProClient()
    try:
        swagger_spec = await _fetch_swagger_spec()
    except Exception:
        swagger_spec = {}
    try:
        yield AppContext(client=client, swagger_spec=swagger_spec)
    finally:
        await client.close()


SERVER_INSTRUCTIONS = """\
PensionPro is a plan administration platform for retirement plan service providers (TPAs).

Entity Hierarchy:
  Client (company) → Plan (retirement plan) → Project (tracked workflow) → Task Group → Task → Task Item
  Plan → Plan Cycle (annual period with deadlines and compliance data)
  Plan → Contacts (people associated with the plan via roles)

Key Concepts:
- Projects are created from Project Templates and track multi-step workflows on a Plan.
- Distributions are specialized Projects (IsDistribution=true) with extra fields for participant info, vesting, and 1099 data.
- Tasks flow through a workflow: each Task is assigned to an employee or Worktray, and must be completed in order.
- Worktrays are shared queues where team members can pick up Tasks.
- PlanSponsorLink (PSL) is a client-facing portal for data collection and document access.
- Notes can be attached to Plans, Projects, Tasks, and Contacts.
- Files include Project Files (general) and Distribution Files (distribution-specific).

Use search_help_articles to find detailed PensionPro documentation on any topic.
Use search_api_paths and get_api_schema to explore the PensionPro REST API.
"""

mcp = FastMCP(
    "PensionPro",
    instructions=SERVER_INSTRUCTIONS,
    lifespan=app_lifespan,
)


# --- Plan tools ---


@mcp.tool(name="search_plans")
@pipeline.wrap
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
@pipeline.wrap
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
@pipeline.wrap
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
@pipeline.wrap
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
@pipeline.wrap
async def _get_project_details(
    ctx: Context[ServerSession, AppContext],
    project_id: int,
) -> dict:
    """Get a project with its task groups, tasks, participants, notes, and files."""
    client = ctx.request_context.lifespan_context.client
    return await get_project_details(client, project_id=project_id)


@mcp.tool(name="get_task_group")
@pipeline.wrap
async def _get_task_group(
    ctx: Context[ServerSession, AppContext],
    task_group_id: int,
) -> dict:
    """Get a task group with all its tasks."""
    client = ctx.request_context.lifespan_context.client
    return await get_task_group(client, task_group_id=task_group_id)


@mcp.tool(name="get_task_details")
@pipeline.wrap
async def _get_task_details(
    ctx: Context[ServerSession, AppContext],
    task_id: int,
) -> dict:
    """Get a single task with its current state, assignment, and notes."""
    client = ctx.request_context.lifespan_context.client
    return await get_task_details(client, task_id=task_id)


@mcp.tool(name="complete_task")
@pipeline.wrap
async def _complete_task(
    ctx: Context[ServerSession, AppContext],
    task_id: int,
) -> dict:
    """Mark a task as complete."""
    client = ctx.request_context.lifespan_context.client
    result = await complete_task(client, task_id=task_id)
    return {"success": True, "task_id": task_id, "result": result}


@mcp.tool(name="uncomplete_task")
@pipeline.wrap
async def _uncomplete_task(
    ctx: Context[ServerSession, AppContext],
    task_id: int,
) -> dict:
    """Undo task completion — revert a task to incomplete."""
    client = ctx.request_context.lifespan_context.client
    result = await uncomplete_task(client, task_id=task_id)
    return {"success": True, "task_id": task_id, "result": result}


@mcp.tool(name="reassign_task")
@pipeline.wrap
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
@pipeline.wrap
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
@pipeline.wrap
async def _search_clients(
    ctx: Context[ServerSession, AppContext],
    name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search and filter clients by company name."""
    client = ctx.request_context.lifespan_context.client
    return await search_clients(client, name=name, limit=limit)


@mcp.tool(name="get_client_details")
@pipeline.wrap
async def _get_client_details(
    ctx: Context[ServerSession, AppContext],
    client_id: int,
) -> dict:
    """Get a client with their plans and notes."""
    client = ctx.request_context.lifespan_context.client
    return await get_client_details(client, client_id=client_id)


@mcp.tool(name="search_contacts")
@pipeline.wrap
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
@pipeline.wrap
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
@pipeline.wrap
async def _get_todo(
    ctx: Context[ServerSession, AppContext],
    todo_id: int,
) -> dict:
    """Get a to-do with its comments."""
    client = ctx.request_context.lifespan_context.client
    return await get_todo(client, todo_id=todo_id)


@mcp.tool(name="create_todo")
@pipeline.wrap
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
@pipeline.wrap
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
@pipeline.wrap
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
@pipeline.wrap
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
@pipeline.wrap
async def _get_worktrays(
    ctx: Context[ServerSession, AppContext],
    active_only: bool = True,
    limit: int = 100,
) -> list[dict]:
    """List all worktrays. Set active_only=false to include inactive worktrays."""
    client = ctx.request_context.lifespan_context.client
    return await get_worktrays(client, active_only=active_only, limit=limit)


@mcp.tool(name="get_worktray")
@pipeline.wrap
async def _get_worktray(
    ctx: Context[ServerSession, AppContext],
    worktray_id: int,
) -> dict:
    """Get a worktray with its members and all active (incomplete) tasks routed to it."""
    client = ctx.request_context.lifespan_context.client
    return await get_worktray(client, worktray_id=worktray_id)


@mcp.tool(name="get_worktray_member_stats")
@pipeline.wrap
async def _get_worktray_member_stats(
    ctx: Context[ServerSession, AppContext],
    worktray_id: int,
    days_back: int = 30,
) -> dict:
    """Get per-member workload, performance, and queue health metrics for a worktray.

    Analyzes completed tasks within the lookback window and current active tasks.
    Returns a compact summary with the top 20 members by activity, aggregate stats,
    and queue health. Full results (all members, individual task lists, overdue task
    details) are written to a cache file and available via the worktray-stats resource.
    """
    client = ctx.request_context.lifespan_context.client
    return await get_worktray_member_stats(client, worktray_id=worktray_id, days_back=days_back)


@mcp.resource("worktray-stats://{worktray_id}", name="worktray_member_stats",
              description="Full worktray member stats from the most recent analysis. "
              "Run get_worktray_member_stats first to populate the cache.",
              mime_type="application/json")
def _worktray_stats_resource(worktray_id: int) -> str:
    """Return cached full stats for a worktray."""
    result = read_cached_stats(worktray_id)
    if result is None:
        return json.dumps({"error": f"No cached stats for worktray {worktray_id}. Run get_worktray_member_stats first."})
    return json.dumps(result)


@mcp.tool(name="get_employee_stats")
@pipeline.wrap
async def _get_employee_stats(
    ctx: Context[ServerSession, AppContext],
    name: str,
    days_back: int = 30,
) -> dict:
    """Get individual employee performance analysis across all worktrays.

    Searches by last name, then computes per-worktray metrics for workload,
    throughput, and quality (rejections and bounce-backs). Returns a compact
    summary; full results cached and available via the employee-stats resource.

    If the name matches multiple employees, returns a candidate list to disambiguate.
    """
    client = ctx.request_context.lifespan_context.client
    return await get_employee_stats(client, name=name, days_back=days_back)


@mcp.resource("employee-stats://{contact_id}", name="employee_stats",
              description="Full employee stats from the most recent analysis. "
              "Run get_employee_stats first to populate the cache.",
              mime_type="application/json")
def _employee_stats_resource(contact_id: int) -> str:
    """Return cached full stats for an employee."""
    result = read_cached_employee_stats(contact_id)
    if result is None:
        return json.dumps({"error": f"No cached stats for employee {contact_id}. Run get_employee_stats first."})
    return json.dumps(result)


# --- Swagger / API reference tools ---


@mcp.tool(name="search_api_paths")
async def _search_api_paths(
    ctx: Context[ServerSession, AppContext],
    keyword: str,
) -> list[dict]:
    """Search PensionPro API endpoints by keyword. Use this to discover available API paths."""
    spec = ctx.request_context.lifespan_context.swagger_spec
    if not spec:
        return [{"error": "Swagger spec not available"}]
    return search_paths(spec, keyword=keyword)


@mcp.tool(name="get_api_endpoint")
async def _get_api_endpoint(
    ctx: Context[ServerSession, AppContext],
    path: str,
    raw: bool = False,
) -> dict | str:
    """Get details for a specific API endpoint. Returns a compact summary by default. Set raw=true for the full JSON schema."""
    spec = ctx.request_context.lifespan_context.swagger_spec
    if not spec:
        return {"error": "Swagger spec not available"}
    return get_endpoint(spec, path=path, raw=raw)


@mcp.tool(name="search_api_schemas")
async def _search_api_schemas(
    ctx: Context[ServerSession, AppContext],
    keyword: str,
) -> list[dict]:
    """Search PensionPro API data models by keyword. Use this to discover field names and types."""
    spec = ctx.request_context.lifespan_context.swagger_spec
    if not spec:
        return [{"error": "Swagger spec not available"}]
    return search_schemas(spec, keyword=keyword)


@mcp.tool(name="get_api_schema")
async def _get_api_schema(
    ctx: Context[ServerSession, AppContext],
    name: str,
    raw: bool = False,
) -> dict | str:
    """Get the definition of a specific API data model/schema. Returns a compact summary by default. Set raw=true for the full JSON schema."""
    spec = ctx.request_context.lifespan_context.swagger_spec
    if not spec:
        return {"error": "Swagger spec not available"}
    return get_schema(spec, name=name, raw=raw)


# --- Help article tools ---


@mcp.tool(name="search_help_articles")
async def _search_help_articles(
    ctx: Context[ServerSession, AppContext],
    keyword: str,
    section: str | None = None,
) -> list[dict]:
    """Search PensionPro help center articles by keyword. Optionally filter by section name. Use list_help_sections to see available sections."""
    return search_help(keyword=keyword, section=section)


@mcp.tool(name="get_help_article")
async def _get_help_article(
    ctx: Context[ServerSession, AppContext],
    article_id: int,
) -> dict:
    """Get the full content of a PensionPro help article by its ID."""
    return get_help_article(article_id=article_id)


@mcp.tool(name="list_help_sections")
async def _list_help_sections(
    ctx: Context[ServerSession, AppContext],
) -> list[dict]:
    """List all available PensionPro help center sections with article counts."""
    return list_help_sections()


def main() -> None:
    """CLI entry point."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
