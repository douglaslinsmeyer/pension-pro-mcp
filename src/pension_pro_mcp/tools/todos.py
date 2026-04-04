"""To-do management tools."""

from typing import Any

from pension_pro_mcp.client import PensionProClient

ENTITY_TYPE_PLAN = 1
ENTITY_TYPE_PROJECT = 4
ENTITY_TYPE_CONTACT = 7


async def search_todos(
    client: PensionProClient,
    status: str | None = None,
    priority: str | None = None,
    plan_id: int | None = None,
    project_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search and filter to-dos."""
    filters: dict[str, str] = {}
    if status:
        filters["ToDoStatus.DisplayName"] = status
    if priority:
        filters["Priority.DisplayName"] = priority

    if plan_id:
        endpoint = f"/plans/{plan_id}/todos"
    elif project_id:
        endpoint = f"/projects/{project_id}/todos"
    else:
        endpoint = "/todos"

    return await client.get_list(endpoint, filters=filters, top=limit, max_total=limit)


async def get_todo(
    client: PensionProClient,
    todo_id: int,
) -> dict[str, Any]:
    """Get a to-do with its comments."""
    todo = await client.get(f"/todos/{todo_id}")
    comments = await client.get(f"/todos/{todo_id}/todocomments")
    # The todo's link is included in the todo record as ToDoLink
    return {
        "todo": todo,
        "comments": comments,
        "link": todo.get("ToDoLink"),
    }


async def create_todo(
    client: PensionProClient,
    subject: str,
    description: str | None = None,
    priority_id: int | None = None,
    due_date: str | None = None,
    status_id: int | None = None,
    assigned_to_contact_id: int | None = None,
    plan_id: int | None = None,
    project_id: int | None = None,
    contact_id: int | None = None,
) -> dict[str, Any]:
    """Create a new to-do, optionally linked to a plan, project, or contact."""
    data: dict[str, Any] = {
        "ToDoName": subject,
        "HasBeenWarned": False,
    }
    if description:
        data["Description"] = description
    if priority_id:
        data["PriorityId"] = priority_id
    if due_date:
        data["DueOn"] = due_date
    if status_id:
        data["ToDoStatusId"] = status_id
    if assigned_to_contact_id:
        data["AssignedToContactId"] = assigned_to_contact_id

    if plan_id:
        data["ToDoLink"] = {"EntityId": plan_id, "EntityTypeId": ENTITY_TYPE_PLAN, "HasBeenWarned": False}
    elif project_id:
        data["ToDoLink"] = {"EntityId": project_id, "EntityTypeId": ENTITY_TYPE_PROJECT, "HasBeenWarned": False}
    elif contact_id:
        data["ToDoLink"] = {"EntityId": contact_id, "EntityTypeId": ENTITY_TYPE_CONTACT, "HasBeenWarned": False}

    return await client.post("/todos", data=data)


async def update_todo(
    client: PensionProClient,
    todo_id: int,
    subject: str | None = None,
    description: str | None = None,
    status_id: int | None = None,
    priority_id: int | None = None,
    due_date: str | None = None,
) -> dict[str, Any]:
    """Update an existing to-do. Fetches current state first, then applies changes."""
    current = await client.get(f"/todos/{todo_id}")
    update_data: dict[str, Any] = {
        "Id": current["Id"],
        "DataKey": current.get("DataKey", ""),
        "ToDoName": subject if subject is not None else current.get("ToDoName", ""),
        "Description": description if description is not None else current.get("Description", ""),
        "ToDoStatusId": status_id if status_id is not None else current.get("ToDoStatusId", 0),
        "PriorityId": priority_id if priority_id is not None else current.get("PriorityId", 0),
        "DueOn": due_date if due_date is not None else current.get("DueOn"),
        "AssignedToContactId": current.get("AssignedToContactId", 0),
        "AssignedToTeamId": current.get("AssignedToTeamId", 0),
        "CompletedOn": current.get("CompletedOn"),
        "StartedOn": current.get("StartedOn"),
        "PercentageCompleted": current.get("PercentageCompleted", 0),
        "HasBeenWarned": current.get("HasBeenWarned", False),
        "IsDeactivated": current.get("IsDeactivated", False),
    }
    return await client.put(f"/todos/{todo_id}", data=update_data)
