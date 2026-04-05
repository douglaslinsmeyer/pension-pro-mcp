"""Worktray tools."""

import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from pension_pro_mcp.client import PensionProClient


def _parse_dt(value: str | None) -> datetime | None:
    """Parse a datetime string from the API (ISO 8601 or US format)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        # Handle US format: "MM/DD/YYYY hh:mm:ss AM/PM"
        try:
            return datetime.strptime(value, "%m/%d/%Y %I:%M:%S %p").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


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


def _compute_performance_stats(
    completed_tasks: list[dict[str, Any]],
    members: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute per-member performance stats from completed tasks."""
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
            "performance": {
                "tasks_completed": 0,
                "avg_completion_hours": None,
                "avg_pickup_hours": None,
                "rejection_rate": 0.0,
                "task_type_breakdown": [],
            },
        }
        member_map[cid] = entry
        member_list.append(entry)

    # Group tasks by assignee
    tasks_by_assignee: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for task in completed_tasks:
        assignee = task.get("AssignedToId")
        if assignee is not None:
            tasks_by_assignee[assignee].append(task)

    all_completion_hours: list[float] = []

    for cid, entry in member_map.items():
        tasks = tasks_by_assignee.get(cid, [])
        entry["performance"]["tasks_completed"] = len(tasks)

        completion_hours: list[float] = []
        pickup_hours: list[float] = []
        total_rejections = 0
        type_counts: Counter[str] = Counter()

        for task in tasks:
            active = _parse_dt(task.get("TaskActive"))
            completed = _parse_dt(task.get("DateCompleted"))
            ack = _parse_dt(task.get("AcknowledgeDate"))

            if active and completed:
                hours = (completed - active).total_seconds() / 3600
                completion_hours.append(hours)
                all_completion_hours.append(hours)

            if active and ack:
                pickup_hours.append((ack - active).total_seconds() / 3600)

            total_rejections += task.get("Rejections") or 0
            type_counts[task.get("TaskName", "Unknown")] += 1

        if completion_hours:
            entry["performance"]["avg_completion_hours"] = round(
                sum(completion_hours) / len(completion_hours), 1
            )
        if pickup_hours:
            entry["performance"]["avg_pickup_hours"] = round(
                sum(pickup_hours) / len(pickup_hours), 1
            )
        if tasks:
            entry["performance"]["rejection_rate"] = round(total_rejections / len(tasks), 2)
        entry["performance"]["task_type_breakdown"] = [
            {"task_name": name, "count": count}
            for name, count in type_counts.most_common()
        ]

    team_avg = None
    if all_completion_hours:
        team_avg = round(sum(all_completion_hours) / len(all_completion_hours), 1)

    return {
        "members": member_list,
        "aggregate": {
            "total_completed": len(completed_tasks),
            "team_avg_completion_hours": team_avg,
        },
    }


def _compute_queue_health(
    active_tasks: list[dict[str, Any]],
    completed_tasks: list[dict[str, Any]],
    days_back: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute queue health metrics from active and completed tasks."""
    if now is None:
        now = datetime.now(timezone.utc)

    cutoff = now - timedelta(days=days_back)

    # Throughput
    throughput_per_day = round(len(completed_tasks) / days_back, 2) if days_back > 0 else 0.0

    # Intake: union of active + completed, deduplicated, added within window
    seen_ids: set[int] = set()
    all_tasks: list[dict[str, Any]] = []
    for task in completed_tasks + active_tasks:
        tid = task.get("Id")
        if tid not in seen_ids:
            seen_ids.add(tid)
            all_tasks.append(task)

    intake_count = 0
    for task in all_tasks:
        added = _parse_dt(task.get("DateAdded"))
        if added and added >= cutoff:
            intake_count += 1

    intake_per_day = round(intake_count / days_back, 2) if days_back > 0 else 0.0

    # Oldest active task
    oldest_age = 0
    for task in active_tasks:
        age = _task_age_days(task, now)
        if age > oldest_age:
            oldest_age = age

    # Overdue tasks
    overdue_tasks: list[dict[str, Any]] = []
    for task in active_tasks:
        days_to_comp = task.get("DaysToComp")
        if days_to_comp is None:
            continue
        age = _task_age_days(task, now)
        if age > days_to_comp:
            overdue_tasks.append({
                "task_id": task["Id"],
                "task_name": task.get("TaskName", "Unknown"),
                "project": _task_project_name(task),
                "age_days": age,
                "days_to_comp": days_to_comp,
            })

    return {
        "throughput_per_day": throughput_per_day,
        "intake_per_day": intake_per_day,
        "queue_growing": intake_per_day > throughput_per_day,
        "oldest_active_task_age_days": oldest_age,
        "overdue_count": len(overdue_tasks),
        "overdue_tasks": overdue_tasks,
    }


async def get_worktray_member_stats(
    client: PensionProClient,
    worktray_id: int,
    days_back: int = 30,
) -> dict[str, Any]:
    """Get per-member workload, performance, and queue health metrics for a worktray."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    completed_tasks, active_tasks, all_members = await asyncio.gather(
        client.get_list(
            "/tasks",
            filters={"TeamId": str(worktray_id), "DateCompleted__ge": cutoff_iso},
            expand=["AssignedTo", "TaskGroup($expand=Project)"],
            top=1000,
            max_total=10000,
        ),
        client.get_list(
            "/tasks",
            filters={"TeamId": str(worktray_id), "DateCompleted": "null"},
            expand=["AssignedTo", "TaskGroup($expand=Project)"],
            top=1000,
            max_total=10000,
        ),
        client.get_list(
            "/worktrayMembers",
            expand=["Contact"],
            top=1000,
            max_total=5000,
        ),
    )

    members = [m for m in all_members if m.get("WorktrayID") == worktray_id]

    workload = _compute_workload_stats(active_tasks, members)
    performance = _compute_performance_stats(completed_tasks, members)
    queue_health = _compute_queue_health(active_tasks, completed_tasks, days_back)

    # Merge per-member results from workload and performance
    merged_members: list[dict[str, Any]] = []
    perf_by_id = {m["contact_id"]: m["performance"] for m in performance["members"]}
    for m in workload["members"]:
        m["performance"] = perf_by_id.get(m["contact_id"], {})
        merged_members.append(m)

    return {
        "worktray_id": worktray_id,
        "period_days": days_back,
        "members": merged_members,
        "aggregate": {
            "workload": workload["aggregate"],
            "performance": performance["aggregate"],
            "queue_health": queue_health,
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
