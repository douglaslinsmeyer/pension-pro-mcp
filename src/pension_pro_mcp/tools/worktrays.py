"""Worktray tools."""

from typing import Any

from pension_pro_mcp.client import PensionProClient


async def get_worktrays(
    client: PensionProClient,
    active_only: bool = True,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List all worktrays."""
    filters: dict[str, str] = {}
    if active_only:
        filters["IsActive"] = "true"
    return await client.get_list("/worktrays", filters=filters, top=limit, max_total=limit)


async def get_worktray(
    client: PensionProClient,
    worktray_id: int,
) -> dict[str, Any]:
    """Get a worktray with its members and active tasks."""
    worktray = await client.get(f"/worktrays/{worktray_id}")
    members = await client.get_list(
        "/worktrayMembers",
        filters={"WorktrayID": str(worktray_id)},
        top=200,
        max_total=200,
    )
    tasks = await client.get_list(
        "/tasks",
        filters={"TeamId": str(worktray_id), "DateCompleted": "null"},
        top=200,
        max_total=200,
    )
    return {
        "worktray": worktray,
        "members": members,
        "active_tasks": tasks,
    }
