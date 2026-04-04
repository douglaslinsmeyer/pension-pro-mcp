"""Project and task workflow tools."""

from typing import Any

from pension_pro_mcp.client import PensionProClient


async def search_projects(
    client: PensionProClient,
    status: str | None = None,
    project_type: str | None = None,
    plan_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search and filter projects."""
    filters: dict[str, str] = {}
    if status:
        filters["ProjectStatus.DisplayName"] = status
    if project_type:
        filters["ProjectType.DisplayName"] = project_type

    endpoint = f"/plans/{plan_id}/projects" if plan_id else "/projects"
    return await client.get_list(endpoint, filters=filters, top=limit, max_total=limit)


async def get_project_details(
    client: PensionProClient,
    project_id: int,
) -> dict[str, Any]:
    """Get a project with full task and participant details."""
    project = await client.get(f"/projects/{project_id}")
    task_groups = await client.get(f"/projects/{project_id}/taskgroups")
    tasks = await client.get(f"/projects/{project_id}/tasks")
    participants = await client.get(f"/projects/{project_id}/participants")
    notes = await client.get(f"/projects/{project_id}/notes")
    project_files = await client.get(f"/projects/{project_id}/projectfiles")

    result: dict[str, Any] = {
        "project": project,
        "task_groups": task_groups,
        "tasks": tasks,
        "participants": participants,
        "notes": notes,
        "project_files": project_files,
    }

    if project.get("IsDistribution"):
        result["distribution_files"] = await client.get(f"/projects/{project_id}/distributionfiles")

    return result


async def get_task_group(
    client: PensionProClient,
    task_group_id: int,
) -> dict[str, Any]:
    """Get a task group with all its tasks."""
    task_group = await client.get(f"/taskgroups/{task_group_id}")
    tasks = await client.get(f"/taskgroups/{task_group_id}/tasks")
    return {
        "task_group": task_group,
        "tasks": tasks,
    }


async def get_task_details(
    client: PensionProClient,
    task_id: int,
) -> dict[str, Any]:
    """Get a single task with its current state and notes."""
    task = await client.get(f"/tasks/{task_id}")
    notes = await client.get(f"/tasks/{task_id}/notes")
    return {
        "task": task,
        "notes": notes,
    }


async def complete_task(client: PensionProClient, task_id: int) -> Any:
    """Mark a task as complete."""
    return await client.put(f"/tasks/{task_id}/completetask")


async def uncomplete_task(client: PensionProClient, task_id: int) -> Any:
    """Undo task completion."""
    return await client.put(f"/tasks/{task_id}/uncompletetask")


async def reassign_task(client: PensionProClient, task_id: int, assigned_to_id: int) -> Any:
    """Reassign a task to a different employee."""
    return await client.put(f"/tasks/employee/{task_id}/{assigned_to_id}")


async def create_project_from_template(
    client: PensionProClient, plan_id: int, template_id: int
) -> dict[str, Any]:
    """Create a new project on a plan from a project template."""
    return await client.post("/projects", data={
        "PlanId": plan_id,
        "ProjectTemplateId": template_id,
        "HasBeenWarned": False,
    })
