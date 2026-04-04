"""Worktray tools."""

from collections import Counter
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
    """Get a worktray with its members and a summary of active tasks."""
    worktray = await client.get(f"/worktrays/{worktray_id}")
    all_members = await client.get_list("/worktrayMembers", top=1000, max_total=5000)
    members = [m for m in all_members if m.get("WorktrayID") == worktray_id]
    tasks = await client.get_list(
        "/tasks",
        filters={"TeamId": str(worktray_id), "DateCompleted": "null"},
        top=1000,
        max_total=10000,
    )

    # Build summary
    task_type_counts = Counter(t.get("TaskName", "Unknown") for t in tasks)
    assignee_counts = Counter(t.get("AssignedToId") for t in tasks)
    unassigned = assignee_counts.pop(None, 0)

    return {
        "worktray": worktray,
        "member_count": len(members),
        "members": [{"contactID": m["contactID"], "RoleID": m["RoleID"]} for m in members],
        "active_task_count": len(tasks),
        "task_summary": {
            "by_type": [
                {"task_name": name, "count": count}
                for name, count in task_type_counts.most_common(20)
            ],
            "by_assignee": [
                {"assigned_to_id": aid, "count": count}
                for aid, count in assignee_counts.most_common(20)
            ],
            "unassigned_count": unassigned,
        },
    }
