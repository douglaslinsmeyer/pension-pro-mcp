"""Analytics tools for cross-cutting workflow metrics."""

import asyncio
import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

from pension_pro_mcp.client import PensionProClient


def _parse_dt(value: str | None) -> datetime | None:
    """Parse a datetime string from the API (ISO 8601 or US format)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(value, "%m/%d/%Y %I:%M:%S %p").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return None


def _compute_cycle_times(task_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group completed task groups by project template and compute cycle time stats.

    Each task group must have a "_template_id" and "_template_name" key injected
    by the caller. Cycle time uses DateActivated (preferred) or DateAdded as the
    start date. Returns a list of per-template stat dicts, sorted by
    groups_completed descending.
    """
    by_template: dict[int, dict[str, Any]] = {}
    for tg in task_groups:
        activated = _parse_dt(tg.get("DateActivated")) or _parse_dt(tg.get("DateAdded"))
        completed = _parse_dt(tg.get("DateCompleted"))
        if not activated or not completed:
            continue

        template_id = tg.get("_template_id")
        template_name = tg.get("_template_name", "Unknown")
        if template_id is None:
            continue

        if template_id not in by_template:
            by_template[template_id] = {
                "template_id": template_id,
                "template_name": template_name,
                "cycle_days": [],
                "sla_met": 0,
                "sla_total": 0,
                "groups_without_due_date": 0,
            }

        entry = by_template[template_id]
        cycle = (completed - activated).total_seconds() / 86400
        entry["cycle_days"].append(cycle)

        due = _parse_dt(tg.get("DateDue"))
        if due:
            entry["sla_total"] += 1
            if completed <= due:
                entry["sla_met"] += 1
        else:
            entry["groups_without_due_date"] += 1

    results: list[dict[str, Any]] = []
    for entry in by_template.values():
        days = entry["cycle_days"]
        sla_pct = (
            round(entry["sla_met"] / entry["sla_total"] * 100, 1)
            if entry["sla_total"] > 0
            else None
        )
        results.append({
            "template_id": entry["template_id"],
            "template_name": entry["template_name"],
            "groups_completed": len(days),
            "avg_cycle_days": round(statistics.mean(days), 1),
            "median_cycle_days": round(statistics.median(days), 1),
            "min_cycle_days": round(min(days), 1),
            "max_cycle_days": round(max(days), 1),
            "sla_adherence_pct": sla_pct,
            "groups_without_due_date": entry["groups_without_due_date"],
        })

    return sorted(results, key=lambda x: x["groups_completed"], reverse=True)


def _compute_step_durations(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute per-step duration for tasks within a single task group.

    Tasks are sorted by Order. Steps with a None Order, missing DateActivated or
    DateCompleted, or a negative duration (data quality issue) are skipped.
    Returns a list of step dicts with order, task_name, duration_days.
    """
    sorted_tasks = sorted(
        (t for t in tasks if t.get("Order") is not None),
        key=lambda t: t["Order"],
    )
    steps: list[dict[str, Any]] = []
    for task in sorted_tasks:
        activated = _parse_dt(task.get("DateActivated"))
        completed = _parse_dt(task.get("DateCompleted"))
        if not activated or not completed:
            continue
        duration = (completed - activated).total_seconds() / 86400
        if duration < 0:
            continue
        steps.append({
            "order": task.get("Order"),
            "task_name": task.get("TaskName", "Unknown"),
            "duration_days": round(duration, 1),
        })
    return steps


def _aggregate_step_durations(
    all_steps: list[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Aggregate per-step durations across multiple task groups and identify the bottleneck.

    Groups step data by order, computes avg/median duration, marks the step with
    the highest avg duration as the bottleneck.
    """
    if not all_steps:
        return []

    by_order: dict[int, dict[str, Any]] = {}
    for group_steps in all_steps:
        for step in group_steps:
            order = step["order"]
            if order not in by_order:
                by_order[order] = {
                    "order": order,
                    "task_name": step["task_name"],
                    "durations": [],
                }
            by_order[order]["durations"].append(step["duration_days"])

    results: list[dict[str, Any]] = []
    for entry in sorted(by_order.values(), key=lambda x: x["order"]):
        durations = entry["durations"]
        results.append({
            "order": entry["order"],
            "task_name": entry["task_name"],
            "avg_duration_days": round(statistics.mean(durations), 1),
            "median_duration_days": round(statistics.median(durations), 1),
            "is_bottleneck": False,
        })

    if results:
        bottleneck = max(results, key=lambda x: x["avg_duration_days"])
        bottleneck["is_bottleneck"] = True

    return results


async def get_task_group_cycle_times(
    client: PensionProClient,
    days_back: int = 90,
    plan_id: int | None = None,
    template_id: int | None = None,
    include_steps: bool = False,
) -> dict[str, Any]:
    """Compute task group cycle times segmented by project template.

    Fetches completed projects within the lookback window, then retrieves their
    task groups via project-scoped endpoints. Groups by project template and
    computes cycle time statistics. When include_steps is True, also fetches
    tasks per group to identify per-step bottlenecks.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_back)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Fetch completed projects, then filter by date in Python
    # (PensionPro's OData doesn't reliably support ge/le on date fields)
    filters: dict[str, str] = {
        "ProjectStatus.DisplayName": "Completed",
    }
    if template_id is not None:
        filters["ProjectTemplateId"] = str(template_id)

    endpoint = f"/plans/{plan_id}/projects" if plan_id else "/projects"
    all_projects = await client.get_list(
        endpoint,
        filters=filters,
        orderby="CompletedOn desc",
        top=1000,
        max_total=10000,
    )

    # Post-filter by completion date — orderby ensures most recent come first,
    # so we stop paginating once we pass the cutoff window.
    projects: list[dict[str, Any]] = []
    for p in all_projects:
        completed = _parse_dt(p.get("CompletedOn"))
        if completed and completed >= cutoff:
            projects.append(p)

    # Fetch task groups for each project, concurrency-limited
    sem = asyncio.Semaphore(10)

    async def fetch_task_groups(project: dict[str, Any]) -> list[dict[str, Any]]:
        async with sem:
            groups = await client.get_list(
                f"/projects/{project['Id']}/taskgroups"
            )
            # Inject template info from the parent project into each group
            for g in groups:
                g["_template_id"] = project.get("ProjectTemplateId")
                g["_template_name"] = project.get("CombinedName") or project.get("Name", "Unknown")
            return groups

    project_group_lists = await asyncio.gather(
        *(fetch_task_groups(p) for p in projects)
    )

    # Flatten all task groups
    all_task_groups: list[dict[str, Any]] = []
    for groups in project_group_lists:
        all_task_groups.extend(groups)

    by_template = _compute_cycle_times(all_task_groups)

    # Fetch per-step data if requested
    if include_steps and all_task_groups:
        if len(all_task_groups) > 500:
            logger.warning(
                "include_steps=True with %d task groups — this may be slow",
                len(all_task_groups),
            )
        # Group task_group IDs by template
        groups_by_template: dict[int, list[int]] = {}
        for tg in all_task_groups:
            tid = tg.get("_template_id")
            start = _parse_dt(tg.get("DateActivated")) or _parse_dt(tg.get("DateAdded"))
            if tid is not None and start:
                groups_by_template.setdefault(tid, []).append(tg["Id"])

        async def fetch_tasks(group_id: int) -> list[dict[str, Any]]:
            async with sem:
                return await client.get_list(f"/taskgroups/{group_id}/tasks")

        for template_entry in by_template:
            tid = template_entry["template_id"]
            group_ids = groups_by_template.get(tid, [])
            task_lists = await asyncio.gather(
                *(fetch_tasks(gid) for gid in group_ids)
            )
            all_steps = [_compute_step_durations(tasks) for tasks in task_lists]
            all_steps = [s for s in all_steps if s]
            template_entry["steps"] = _aggregate_step_durations(all_steps)

    valid_count = sum(t["groups_completed"] for t in by_template)

    return {
        "by_template": by_template,
        "summary": {
            "total_groups_completed": valid_count,
            "templates_analyzed": len(by_template),
            "period_days": days_back,
            "cutoff_date": cutoff_iso,
        },
    }
