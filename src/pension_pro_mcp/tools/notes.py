"""Notes tools."""

from typing import Any

from pension_pro_mcp.client import PensionProClient


async def add_note(
    client: PensionProClient,
    text: str,
    plan_id: int | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
    contact_id: int | None = None,
    category_id: int | None = None,
) -> dict[str, Any]:
    """Add a note to a plan, project, task, or contact."""
    if not any([plan_id, project_id, task_id, contact_id]):
        raise ValueError("At least one entity ID (plan_id, project_id, task_id, contact_id) must be provided")

    data: dict[str, Any] = {
        "NoteText": text,
        "HasBeenWarned": False,
        "Archived": False,
        "IsImportant": False,
    }
    if plan_id:
        data["PlanId"] = plan_id
    if project_id:
        data["ProjectId"] = project_id
    if task_id:
        data["TaskId"] = task_id
    if contact_id:
        data["ContactId"] = contact_id
    if category_id:
        data["NoteCategoryId"] = category_id

    return await client.post("/notes", data=data)


async def get_notes(
    client: PensionProClient,
    plan_id: int | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
    contact_id: int | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Get notes for an entity (plan, project, task, or contact)."""
    if plan_id:
        endpoint = f"/plans/{plan_id}/notes"
    elif project_id:
        endpoint = f"/projects/{project_id}/notes"
    elif task_id:
        endpoint = f"/tasks/{task_id}/notes"
    elif contact_id:
        endpoint = f"/contacts/{contact_id}/notes"
    else:
        raise ValueError("At least one entity ID (plan_id, project_id, task_id, contact_id) must be provided")

    return await client.get_list(endpoint, top=limit, max_total=limit)
