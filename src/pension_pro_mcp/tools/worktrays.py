"""Worktray tools."""

import asyncio
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pension_pro_mcp.client import PensionProClient


def _stats_cache_dir() -> Path:
    """Return the platform-appropriate cache directory for stats files."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "pension-pro-mcp" / "stats"


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


async def _resolve_employee(
    client: PensionProClient,
    name: str,
) -> dict[str, Any]:
    """Search for an employee by last name and resolve to a single contact.

    Returns:
        {"status": "found", "contact_id": int, "name": str} for a single match
        {"status": "ambiguous", "candidates": [...]} for multiple matches
        {"status": "not_found"} for no matches
    """
    contacts = await client.get_list(
        "/contacts",
        filters={"LastName__contains": name, "SystemEmployee": "true"},
        expand=["Employee"],
        top=50,
        max_total=50,
    )

    # Filter to active employees
    employees = []
    for c in contacts:
        emp = c.get("Employee")
        if emp and isinstance(emp, dict) and emp.get("Active"):
            employees.append(c)

    if not employees:
        return {"status": "not_found"}

    if len(employees) == 1:
        c = employees[0]
        return {
            "status": "found",
            "contact_id": c["Id"],
            "name": f"{c.get('FirstName', '')} {c.get('LastName', '')}".strip(),
        }

    return {
        "status": "ambiguous",
        "candidates": [
            {
                "contact_id": c["Id"],
                "name": f"{c.get('FirstName', '')} {c.get('LastName', '')}".strip(),
            }
            for c in employees
        ],
    }


def _compute_employee_workload(
    active_tasks: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute workload metrics for an employee from their active tasks."""
    if now is None:
        now = datetime.now(timezone.utc)

    oldest_age = 0
    tasks: list[dict[str, Any]] = []
    for task in active_tasks:
        age = _task_age_days(task, now)
        if age > oldest_age:
            oldest_age = age
        tasks.append({
            "task_name": task.get("TaskName", "Unknown"),
            "project": _task_project_name(task),
            "age_days": age,
        })

    return {
        "active_task_count": len(active_tasks),
        "oldest_task_age_days": oldest_age,
        "tasks": tasks,
    }


def _compute_employee_throughput(
    completed_tasks: list[dict[str, Any]],
    days_back: int,
) -> dict[str, Any]:
    """Compute throughput metrics for an employee from their completed tasks."""
    completion_hours: list[float] = []
    pickup_hours: list[float] = []
    type_counts: Counter[str] = Counter()
    project_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for task in completed_tasks:
        active = _parse_dt(task.get("TaskActive"))
        completed = _parse_dt(task.get("DateCompleted"))
        ack = _parse_dt(task.get("AcknowledgeDate"))

        if active and completed:
            completion_hours.append((completed - active).total_seconds() / 3600)
        if active and ack:
            pickup_hours.append((ack - active).total_seconds() / 3600)

        type_counts[task.get("TaskName", "Unknown")] += 1
        project_name = _task_project_name(task) or "Unknown"
        project_groups[project_name].append(task)

    # Per-project breakdown
    by_project: list[dict[str, Any]] = []
    for proj_name, proj_tasks in project_groups.items():
        proj_hours: list[float] = []
        for t in proj_tasks:
            a = _parse_dt(t.get("TaskActive"))
            c = _parse_dt(t.get("DateCompleted"))
            if a and c:
                proj_hours.append((c - a).total_seconds() / 3600)
        by_project.append({
            "project": proj_name,
            "tasks_completed": len(proj_tasks),
            "avg_completion_hours": round(sum(proj_hours) / len(proj_hours), 1) if proj_hours else None,
        })
    by_project.sort(key=lambda x: x["tasks_completed"], reverse=True)

    return {
        "tasks_completed": len(completed_tasks),
        "avg_completion_hours": round(sum(completion_hours) / len(completion_hours), 1) if completion_hours else None,
        "avg_pickup_hours": round(sum(pickup_hours) / len(pickup_hours), 1) if pickup_hours else None,
        "tasks_per_day": round(len(completed_tasks) / days_back, 2) if days_back > 0 else 0.0,
        "task_type_breakdown": [
            {"task_name": name, "count": count}
            for name, count in type_counts.most_common()
        ],
        "by_project": by_project,
    }


def _compute_employee_quality(
    completed_tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute quality metrics (rejections and bounce-backs) from completed tasks."""
    total = len(completed_tasks)
    total_rejections = 0
    tasks_with_rejections = 0
    bounce_back_count = 0

    for task in completed_tasks:
        rejections = task.get("Rejections") or 0
        total_rejections += rejections
        if rejections > 0:
            tasks_with_rejections += 1
        if task.get("Rejected"):
            bounce_back_count += 1

    return {
        "rejection_rate": round(tasks_with_rejections / total, 2) if total else 0.0,
        "total_rejections": total_rejections,
        "bounce_back_count": bounce_back_count,
        "bounce_back_rate": round(bounce_back_count / total, 2) if total else 0.0,
    }


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
    """Compute per-member performance stats from completed tasks, grouped by project."""
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
                "by_project": [],
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
    # Aggregate by_project accumulators
    agg_project_data: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"completion_hours": [], "count": 0, "assignees": set()}
    )

    for cid, entry in member_map.items():
        tasks = tasks_by_assignee.get(cid, [])
        entry["performance"]["tasks_completed"] = len(tasks)

        completion_hours: list[float] = []
        pickup_hours: list[float] = []
        total_rejections = 0
        type_counts: Counter[str] = Counter()

        # Group this member's tasks by project
        project_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

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

            project_name = _task_project_name(task) or "Unknown"
            project_groups[project_name].append(task)

            # Feed aggregate
            agg_project_data[project_name]["count"] += 1
            agg_project_data[project_name]["assignees"].add(cid)
            if active and completed:
                hours_val = (completed - active).total_seconds() / 3600
                agg_project_data[project_name]["completion_hours"].append(hours_val)

        # Member totals
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

        # Per-project breakdown for this member
        member_by_project: list[dict[str, Any]] = []
        for proj_name, proj_tasks in project_groups.items():
            proj_completion: list[float] = []
            proj_pickup: list[float] = []
            proj_rejections = 0
            for task in proj_tasks:
                active = _parse_dt(task.get("TaskActive"))
                completed = _parse_dt(task.get("DateCompleted"))
                ack = _parse_dt(task.get("AcknowledgeDate"))
                if active and completed:
                    proj_completion.append((completed - active).total_seconds() / 3600)
                if active and ack:
                    proj_pickup.append((ack - active).total_seconds() / 3600)
                proj_rejections += task.get("Rejections") or 0

            proj_entry: dict[str, Any] = {
                "project": proj_name,
                "tasks_completed": len(proj_tasks),
                "avg_completion_hours": round(sum(proj_completion) / len(proj_completion), 1) if proj_completion else None,
                "avg_pickup_hours": round(sum(proj_pickup) / len(proj_pickup), 1) if proj_pickup else None,
                "rejection_rate": round(proj_rejections / len(proj_tasks), 2),
            }
            member_by_project.append(proj_entry)

        entry["performance"]["by_project"] = sorted(
            member_by_project, key=lambda x: x["tasks_completed"], reverse=True
        )

    team_avg = None
    if all_completion_hours:
        team_avg = round(sum(all_completion_hours) / len(all_completion_hours), 1)

    # Build aggregate by_project
    agg_by_project = sorted(
        [
            {
                "project": name,
                "tasks_completed": info["count"],
                "avg_completion_hours": round(sum(info["completion_hours"]) / len(info["completion_hours"]), 1) if info["completion_hours"] else None,
                "member_count": len(info["assignees"]),
            }
            for name, info in agg_project_data.items()
        ],
        key=lambda x: x["tasks_completed"],
        reverse=True,
    )

    return {
        "members": member_list,
        "aggregate": {
            "total_completed": len(completed_tasks),
            "team_avg_completion_hours": team_avg,
            "by_project": agg_by_project,
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

    # Overdue tasks — individual list and summarized by type
    overdue_tasks: list[dict[str, Any]] = []
    overdue_by_type: dict[str, dict[str, Any]] = {}
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
            name = task.get("TaskName", "Unknown")
            if name not in overdue_by_type:
                overdue_by_type[name] = {"count": 0, "total_age_days": 0, "total_days_over_sla": 0}
            overdue_by_type[name]["count"] += 1
            overdue_by_type[name]["total_age_days"] += age
            overdue_by_type[name]["total_days_over_sla"] += age - days_to_comp

    overdue_summary = sorted(
        [
            {
                "task_name": name,
                "count": info["count"],
                "avg_age_days": round(info["total_age_days"] / info["count"]),
                "avg_days_over_sla": round(info["total_days_over_sla"] / info["count"]),
            }
            for name, info in overdue_by_type.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )

    return {
        "throughput_per_day": throughput_per_day,
        "intake_per_day": intake_per_day,
        "queue_growing": intake_per_day > throughput_per_day,
        "oldest_active_task_age_days": oldest_age,
        "overdue_count": len(overdue_tasks),
        "overdue_tasks": overdue_tasks,
        "overdue_by_type": overdue_summary,
    }


def _compact_member(member: dict[str, Any]) -> dict[str, Any]:
    """Strip task detail lists from a member entry for the compact summary."""
    compact = {
        "contact_id": member["contact_id"],
        "name": member["name"],
        "role_id": member["role_id"],
        "workload": {"active_task_count": member["workload"]["active_task_count"]},
        "performance": {
            k: v for k, v in member["performance"].items()
            if k not in ("task_type_breakdown", "by_project")
        },
    }
    return compact


def _compact_queue_health(queue_health: dict[str, Any]) -> dict[str, Any]:
    """Strip individual overdue_tasks list, keep overdue_by_type summary."""
    return {k: v for k, v in queue_health.items() if k != "overdue_tasks"}


TOP_MEMBERS = 20


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

    # Enrich aggregate by_project with top_performers from per-member data
    agg_by_project = performance["aggregate"].get("by_project", [])
    for proj_entry in agg_by_project:
        proj_name = proj_entry["project"]
        performers: list[dict[str, Any]] = []
        for m in merged_members:
            for mp in m.get("performance", {}).get("by_project", []):
                if mp["project"] == proj_name:
                    performers.append({
                        "name": m["name"],
                        "tasks_completed": mp["tasks_completed"],
                        "avg_completion_hours": mp["avg_completion_hours"],
                    })
                    break
        proj_entry["top_performers"] = sorted(
            performers, key=lambda x: x["tasks_completed"], reverse=True
        )[:3]

    # Build full result
    full_result: dict[str, Any] = {
        "worktray_id": worktray_id,
        "period_days": days_back,
        "member_count": len(merged_members),
        "members": merged_members,
        "aggregate": {
            "workload": workload["aggregate"],
            "performance": performance["aggregate"],
            "queue_health": queue_health,
        },
    }

    # Write full result to cache file
    cache_dir = _stats_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"worktray-{worktray_id}-{days_back}d.json"
    cache_file.write_text(json.dumps(full_result, indent=2))

    # Build compact summary for the tool response
    sorted_members = sorted(
        merged_members,
        key=lambda m: m["performance"].get("tasks_completed", 0),
        reverse=True,
    )
    compact_members = [_compact_member(m) for m in sorted_members[:TOP_MEMBERS]]

    return {
        "worktray_id": worktray_id,
        "period_days": days_back,
        "member_count": len(merged_members),
        "top_members": compact_members,
        "aggregate": {
            "workload": workload["aggregate"],
            "performance": performance["aggregate"],
            "queue_health": _compact_queue_health(queue_health),
        },
        "full_results": str(cache_file),
        "resource_uri": f"worktray-stats://{worktray_id}",
    }


def read_cached_stats(worktray_id: int) -> dict[str, Any] | None:
    """Read cached stats for a worktray, if available."""
    cache_dir = _stats_cache_dir()
    # Find most recent cache file for this worktray
    matches = sorted(cache_dir.glob(f"worktray-{worktray_id}-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        return None
    return json.loads(matches[0].read_text())


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
