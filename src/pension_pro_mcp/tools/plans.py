"""Plan lookup and search tools."""

import asyncio
from typing import Any

from pension_pro_mcp.client import PensionProClient


async def search_plans(
    client: PensionProClient,
    name: str | None = None,
    status: str | None = None,
    plan_type: str | None = None,
    client_name: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search and filter plans."""
    filters: dict[str, str] = {}
    if name:
        filters["SearchText__contains"] = name
    if status:
        filters["Status.DisplayName"] = status
    if plan_type:
        filters["PlanType.DisplayName"] = plan_type
    if client_name:
        filters["Client.CompanyNameId__contains"] = client_name

    return await client.get_list("/plans", filters=filters, top=limit, max_total=limit)


async def get_plan_details(
    client: PensionProClient,
    plan_id: int,
) -> dict[str, Any]:
    """Get comprehensive details for a single plan."""
    plan = await client.get(f"/plans/{plan_id}")
    contacts = await client.get(f"/plans/{plan_id}/plancontactroles")
    plan_cycles = await client.get(f"/plans/{plan_id}/planCycles")
    services = await client.get(f"/plans/{plan_id}/planServicesProvidedLinks")
    investments = await client.get(f"/plans/{plan_id}/investmentproviders")
    fee_schedules = await client.get(f"/plans/{plan_id}/feeschedules")

    return {
        "plan": plan,
        "contacts": contacts,
        "plan_cycles": plan_cycles,
        "services_provided": services,
        "investment_providers": investments,
        "fee_schedules": fee_schedules,
    }


async def get_plan_projects(
    client: PensionProClient,
    plan_id: int,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Get all projects for a plan with task completion summaries."""
    filters: dict[str, str] = {}
    if status:
        filters["ProjectStatus.DisplayName"] = status

    projects = await client.get_list(
        f"/plans/{plan_id}/projects", filters=filters, top=100, max_total=500
    )

    async def _fetch_task_summary(project: dict[str, Any]) -> dict[str, Any]:
        project_id = project["Id"]
        tasks_data = await client.get(f"/projects/{project_id}/tasks")
        # Unwrap paginated response for local computation
        tasks = tasks_data["Values"] if isinstance(tasks_data, dict) and "Values" in tasks_data else tasks_data
        if not isinstance(tasks, list):
            tasks = [tasks]
        completed = sum(1 for t in tasks if t.get("CompletedOn"))
        total = len(tasks)
        return {
            "project": project,
            "task_summary": {
                "total": total,
                "completed": completed,
                "pending": total - completed,
            },
        }

    return await asyncio.gather(*[_fetch_task_summary(p) for p in projects])
