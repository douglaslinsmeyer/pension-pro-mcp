"""Analytics tools for cross-cutting workflow metrics."""

import statistics
from datetime import datetime, timezone
from typing import Any


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

    Returns a list of per-template stat dicts, sorted by groups_completed descending.
    """
    # Group by template
    by_template: dict[int, dict[str, Any]] = {}
    for tg in task_groups:
        activated = _parse_dt(tg.get("DateActivated"))
        completed = _parse_dt(tg.get("DateCompleted"))
        if not activated or not completed:
            continue

        project = tg.get("Project") or {}
        template_id = project.get("ProjectTemplateId")
        if template_id is None:
            continue

        template = project.get("ProjectTemplate") or {}
        template_name = template.get("Name", "Unknown")

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

    # Build result
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
