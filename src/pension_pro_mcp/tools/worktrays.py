"""Worktray tools."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from pension_pro_mcp.client import PensionProClient


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO 8601 datetime string from the API."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _task_age_days(task: dict[str, Any], now: datetime) -> int:
    """Compute task age in days from TaskActive (preferred) or DateAdded."""
    active = _parse_dt(task.get("TaskActive"))
    added = _parse_dt(task.get("DateAdded"))
    reference = active or added
    if reference is None:
        return 0
    return max(0, (now - reference).days)


def _task_project_name(task: dict[str, Any]) -> str | None:
    """Extract project name from expanded TaskGroup.Project."""
    tg = task.get("TaskGroup")
    if tg and isinstance(tg, dict):
        proj = tg.get("Project")
        if proj and isinstance(proj, dict):
            return proj.get("Name")
    return None


def _compute_workload_stats(
    active_tasks: list[dict[str, Any]],
    members: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute per-member workload stats from active tasks."""
    if now is None:
        now = datetime.now(timezone.utc)

    # Build member scaffolding
    member_map: dict[int, dict[str, Any]] = {}
    member_list: list[dict[str, Any]] = []
    for m in members:
        cid = m["contactID"]
        contact = m.get("Contact") or {}
        entry = {
            "contact_id": cid,
            "name": f"{contact.get('FirstName', '')} {contact.get('LastName', '')}".strip(),
            "role_id": m["RoleID"],
            "workload": {
                "active_task_count": 0,
                "tasks": [],
            },
        }
        member_map[cid] = entry
        member_list.append(entry)

    unassigned = 0
    for task in active_tasks:
        assignee = task.get("AssignedToId")
        if assignee is None:
            unassigned += 1
        if assignee and assignee in member_map:
            member_map[assignee]["workload"]["active_task_count"] += 1
            member_map[assignee]["workload"]["tasks"].append({
                "task_name": task.get("TaskName", "Unknown"),
                "project": _task_project_name(task),
                "age_days": _task_age_days(task, now),
            })

    return {
        "members": member_list,
        "aggregate": {
            "total_active": len(active_tasks),
            "unassigned_count": unassigned,
        },
    }


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
