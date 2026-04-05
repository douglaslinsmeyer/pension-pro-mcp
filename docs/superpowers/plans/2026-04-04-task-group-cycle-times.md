# Task Group Cycle Times Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `get_task_group_cycle_times` MCP tool that computes task group cycle times segmented by project template, with optional per-step bottleneck analysis.

**Architecture:** New `tools/analytics.py` module with a public `get_task_group_cycle_times` function and private helpers for cycle time and step duration computation. Queries `/taskgroups` with `$expand=Project($expand=ProjectTemplate)` for template-level stats, and optionally `/taskgroups/{id}/tasks` for per-step bottleneck analysis. Registered as an MCP tool in `server.py`.

**Tech Stack:** Python 3.12, pytest + pytest-asyncio + respx, httpx, FastMCP

---

### Task 1: Scaffold `tools/analytics.py` with `_compute_cycle_times` helper

**Files:**
- Create: `src/pension_pro_mcp/tools/analytics.py`
- Create: `tests/test_analytics.py`

- [ ] **Step 1: Write the failing test for `_compute_cycle_times` with multiple templates**

Create `tests/test_analytics.py`:

```python
"""Tests for analytics tools."""

from datetime import datetime, timezone

import pytest

from pension_pro_mcp.tools.analytics import _compute_cycle_times


class TestComputeCycleTimes:
    def test_groups_by_template_and_computes_stats(self) -> None:
        task_groups = [
            {
                "Id": 1,
                "DateActivated": "2026-01-01T00:00:00Z",
                "DateCompleted": "2026-01-09T00:00:00Z",
                "DateDue": "2026-01-15T00:00:00Z",
                "Project": {
                    "ProjectTemplateId": 10,
                    "ProjectTemplate": {"Name": "DC Distribution Rqst"},
                },
            },
            {
                "Id": 2,
                "DateActivated": "2026-01-05T00:00:00Z",
                "DateCompleted": "2026-01-15T00:00:00Z",
                "DateDue": "2026-01-10T00:00:00Z",
                "Project": {
                    "ProjectTemplateId": 10,
                    "ProjectTemplate": {"Name": "DC Distribution Rqst"},
                },
            },
            {
                "Id": 3,
                "DateActivated": "2026-02-01T00:00:00Z",
                "DateCompleted": "2026-02-04T00:00:00Z",
                "DateDue": "2026-02-10T00:00:00Z",
                "Project": {
                    "ProjectTemplateId": 20,
                    "ProjectTemplate": {"Name": "Annual Valuation"},
                },
            },
        ]

        result = _compute_cycle_times(task_groups)

        assert len(result) == 2

        # Sorted by groups_completed desc — template 10 has 2, template 20 has 1
        dc = result[0]
        assert dc["template_id"] == 10
        assert dc["template_name"] == "DC Distribution Rqst"
        assert dc["groups_completed"] == 2
        assert dc["avg_cycle_days"] == 9.0  # (8 + 10) / 2
        assert dc["median_cycle_days"] == 9.0  # median of [8, 10]
        assert dc["min_cycle_days"] == 8.0
        assert dc["max_cycle_days"] == 10.0
        assert dc["sla_adherence_pct"] == 50.0  # 1 of 2 met SLA
        assert dc["groups_without_due_date"] == 0

        annual = result[1]
        assert annual["template_id"] == 20
        assert annual["groups_completed"] == 1
        assert annual["avg_cycle_days"] == 3.0
        assert annual["sla_adherence_pct"] == 100.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_analytics.py::TestComputeCycleTimes::test_groups_by_template_and_computes_stats -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pension_pro_mcp.tools.analytics'`

- [ ] **Step 3: Write minimal implementation of `_compute_cycle_times`**

Create `src/pension_pro_mcp/tools/analytics.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_analytics.py::TestComputeCycleTimes::test_groups_by_template_and_computes_stats -v`
Expected: PASS

- [ ] **Step 5: Write edge case tests**

Add to `TestComputeCycleTimes` in `tests/test_analytics.py`:

```python
    def test_skips_groups_without_date_activated(self) -> None:
        task_groups = [
            {
                "Id": 1,
                "DateActivated": None,
                "DateCompleted": "2026-01-09T00:00:00Z",
                "DateDue": "2026-01-15T00:00:00Z",
                "Project": {
                    "ProjectTemplateId": 10,
                    "ProjectTemplate": {"Name": "Template A"},
                },
            },
        ]
        result = _compute_cycle_times(task_groups)
        assert result == []

    def test_all_groups_missing_due_date(self) -> None:
        task_groups = [
            {
                "Id": 1,
                "DateActivated": "2026-01-01T00:00:00Z",
                "DateCompleted": "2026-01-05T00:00:00Z",
                "DateDue": None,
                "Project": {
                    "ProjectTemplateId": 10,
                    "ProjectTemplate": {"Name": "Template A"},
                },
            },
        ]
        result = _compute_cycle_times(task_groups)
        assert len(result) == 1
        assert result[0]["sla_adherence_pct"] is None
        assert result[0]["groups_without_due_date"] == 1

    def test_empty_input(self) -> None:
        assert _compute_cycle_times([]) == []
```

- [ ] **Step 6: Run all edge case tests**

Run: `uv run pytest tests/test_analytics.py::TestComputeCycleTimes -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/pension_pro_mcp/tools/analytics.py tests/test_analytics.py
git commit -m "feat: add _compute_cycle_times helper for template-level stats"
```

---

### Task 2: Add `_compute_step_durations` and `_aggregate_step_durations` helpers

**Files:**
- Modify: `src/pension_pro_mcp/tools/analytics.py`
- Modify: `tests/test_analytics.py`

- [ ] **Step 1: Write the failing test for `_compute_step_durations`**

Add to `tests/test_analytics.py`:

```python
from pension_pro_mcp.tools.analytics import _compute_step_durations


class TestComputeStepDurations:
    def test_computes_per_step_timing(self) -> None:
        tasks = [
            {
                "Order": 1,
                "TaskName": "Review Request",
                "DateActivated": "2026-01-01T00:00:00Z",
                "DateCompleted": "2026-01-02T00:00:00Z",
            },
            {
                "Order": 2,
                "TaskName": "Process Distribution",
                "DateActivated": "2026-01-02T00:00:00Z",
                "DateCompleted": "2026-01-05T00:00:00Z",
            },
            {
                "Order": 3,
                "TaskName": "Final Confirmation",
                "DateActivated": "2026-01-05T00:00:00Z",
                "DateCompleted": "2026-01-06T00:00:00Z",
            },
        ]

        result = _compute_step_durations(tasks)

        assert len(result) == 3
        assert result[0] == {"order": 1, "task_name": "Review Request", "duration_days": 1.0}
        assert result[1] == {"order": 2, "task_name": "Process Distribution", "duration_days": 3.0}
        assert result[2] == {"order": 3, "task_name": "Final Confirmation", "duration_days": 1.0}

    def test_skips_steps_with_missing_dates(self) -> None:
        tasks = [
            {
                "Order": 1,
                "TaskName": "Step A",
                "DateActivated": "2026-01-01T00:00:00Z",
                "DateCompleted": "2026-01-02T00:00:00Z",
            },
            {
                "Order": 2,
                "TaskName": "Step B",
                "DateActivated": None,
                "DateCompleted": "2026-01-05T00:00:00Z",
            },
        ]

        result = _compute_step_durations(tasks)
        assert len(result) == 1
        assert result[0]["task_name"] == "Step A"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_analytics.py::TestComputeStepDurations -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `_compute_step_durations`**

Add to `src/pension_pro_mcp/tools/analytics.py`:

```python
def _compute_step_durations(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute per-step duration for tasks within a single task group.

    Tasks are sorted by Order. Steps with missing DateActivated or DateCompleted
    are skipped. Returns a list of step dicts with order, task_name, duration_days.
    """
    sorted_tasks = sorted(tasks, key=lambda t: t.get("Order") or 0)
    steps: list[dict[str, Any]] = []
    for task in sorted_tasks:
        activated = _parse_dt(task.get("DateActivated"))
        completed = _parse_dt(task.get("DateCompleted"))
        if not activated or not completed:
            continue
        duration = (completed - activated).total_seconds() / 86400
        steps.append({
            "order": task.get("Order"),
            "task_name": task.get("TaskName", "Unknown"),
            "duration_days": round(duration, 1),
        })
    return steps
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_analytics.py::TestComputeStepDurations -v`
Expected: PASS

- [ ] **Step 5: Write the failing test for `_aggregate_step_durations`**

Add to `tests/test_analytics.py`:

```python
from pension_pro_mcp.tools.analytics import _aggregate_step_durations


class TestAggregateStepDurations:
    def test_aggregates_across_groups_and_finds_bottleneck(self) -> None:
        all_steps = [
            # Group 1
            [
                {"order": 1, "task_name": "Review", "duration_days": 1.0},
                {"order": 2, "task_name": "Process", "duration_days": 3.0},
                {"order": 3, "task_name": "Confirm", "duration_days": 1.0},
            ],
            # Group 2
            [
                {"order": 1, "task_name": "Review", "duration_days": 2.0},
                {"order": 2, "task_name": "Process", "duration_days": 4.0},
                {"order": 3, "task_name": "Confirm", "duration_days": 0.5},
            ],
        ]

        result = _aggregate_step_durations(all_steps)

        assert len(result) == 3
        assert result[0]["order"] == 1
        assert result[0]["task_name"] == "Review"
        assert result[0]["avg_duration_days"] == 1.5  # (1 + 2) / 2
        assert result[0]["median_duration_days"] == 1.5
        assert result[0]["is_bottleneck"] is False

        assert result[1]["order"] == 2
        assert result[1]["task_name"] == "Process"
        assert result[1]["avg_duration_days"] == 3.5  # (3 + 4) / 2
        assert result[1]["is_bottleneck"] is True  # highest avg

        assert result[2]["order"] == 3
        assert result[2]["is_bottleneck"] is False

    def test_empty_input(self) -> None:
        assert _aggregate_step_durations([]) == []

    def test_single_group(self) -> None:
        all_steps = [
            [
                {"order": 1, "task_name": "Only Step", "duration_days": 5.0},
            ],
        ]
        result = _aggregate_step_durations(all_steps)
        assert len(result) == 1
        assert result[0]["is_bottleneck"] is True
        assert result[0]["avg_duration_days"] == 5.0
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_analytics.py::TestAggregateStepDurations -v`
Expected: FAIL with `ImportError`

- [ ] **Step 7: Implement `_aggregate_step_durations`**

Add to `src/pension_pro_mcp/tools/analytics.py`:

```python
def _aggregate_step_durations(
    all_steps: list[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Aggregate per-step durations across multiple task groups and identify the bottleneck.

    Groups step data by order, computes avg/median duration, marks the step with
    the highest avg duration as the bottleneck.
    """
    if not all_steps:
        return []

    # Collect durations by order
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

    # Compute stats
    results: list[dict[str, Any]] = []
    for entry in sorted(by_order.values(), key=lambda x: x["order"]):
        durations = entry["durations"]
        results.append({
            "order": entry["order"],
            "task_name": entry["task_name"],
            "avg_duration_days": round(statistics.mean(durations), 1),
            "median_duration_days": round(statistics.median(durations), 1),
            "is_bottleneck": False,  # set below
        })

    # Mark bottleneck
    if results:
        bottleneck = max(results, key=lambda x: x["avg_duration_days"])
        bottleneck["is_bottleneck"] = True

    return results
```

- [ ] **Step 8: Run all step duration tests**

Run: `uv run pytest tests/test_analytics.py::TestComputeStepDurations tests/test_analytics.py::TestAggregateStepDurations -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add src/pension_pro_mcp/tools/analytics.py tests/test_analytics.py
git commit -m "feat: add step duration computation and aggregation helpers"
```

---

### Task 3: Implement public `get_task_group_cycle_times` function

**Files:**
- Modify: `src/pension_pro_mcp/tools/analytics.py`
- Modify: `tests/test_analytics.py`

- [ ] **Step 1: Write the failing integration test (without `include_steps`)**

Add to `tests/test_analytics.py`:

```python
import httpx
import respx

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.analytics import get_task_group_cycle_times


class TestGetTaskGroupCycleTimes:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_cycle_times_by_template(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/taskgroups").mock(
            return_value=httpx.Response(200, json=[
                {
                    "Id": 1,
                    "DateActivated": "2026-01-01T00:00:00Z",
                    "DateCompleted": "2026-01-06T00:00:00Z",
                    "DateDue": "2026-01-10T00:00:00Z",
                    "Project": {
                        "ProjectTemplateId": 10,
                        "ProjectTemplate": {"Name": "DC Distribution Rqst"},
                    },
                },
                {
                    "Id": 2,
                    "DateActivated": "2026-01-10T00:00:00Z",
                    "DateCompleted": "2026-01-20T00:00:00Z",
                    "DateDue": "2026-01-15T00:00:00Z",
                    "Project": {
                        "ProjectTemplateId": 10,
                        "ProjectTemplate": {"Name": "DC Distribution Rqst"},
                    },
                },
            ])
        )

        result = await get_task_group_cycle_times(client, days_back=90)

        assert result["summary"]["total_groups_completed"] == 2
        assert result["summary"]["templates_analyzed"] == 1
        assert result["summary"]["period_days"] == 90

        dc = result["by_template"][0]
        assert dc["template_id"] == 10
        assert dc["avg_cycle_days"] == 7.5  # (5 + 10) / 2
        assert dc["sla_adherence_pct"] == 50.0  # 1 of 2 met SLA
        assert "steps" not in dc
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_analytics.py::TestGetTaskGroupCycleTimes::test_returns_cycle_times_by_template -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement `get_task_group_cycle_times` (without step logic)**

Add to `src/pension_pro_mcp/tools/analytics.py`:

```python
import asyncio

from pension_pro_mcp.client import PensionProClient


async def get_task_group_cycle_times(
    client: PensionProClient,
    days_back: int = 90,
    plan_id: int | None = None,
    template_id: int | None = None,
    include_steps: bool = False,
) -> dict[str, Any]:
    """Compute task group cycle times segmented by project template.

    Fetches completed task groups within the lookback window, groups them by
    project template, and computes cycle time statistics. When include_steps
    is True, also fetches tasks per group to identify per-step bottlenecks.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_back)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    filters: dict[str, str] = {"DateCompleted__ge": cutoff_iso}
    if plan_id is not None:
        filters["Project/PlanId"] = str(plan_id)
    if template_id is not None:
        filters["Project/ProjectTemplateId"] = str(template_id)

    task_groups = await client.get_list(
        "/taskgroups",
        filters=filters,
        expand=["Project($expand=ProjectTemplate)"],
        top=1000,
        max_total=10000,
    )

    by_template = _compute_cycle_times(task_groups)

    # Fetch per-step data if requested
    if include_steps and task_groups:
        # Group task_group IDs by template
        groups_by_template: dict[int, list[int]] = {}
        for tg in task_groups:
            project = tg.get("Project") or {}
            tid = project.get("ProjectTemplateId")
            if tid is not None and _parse_dt(tg.get("DateActivated")):
                groups_by_template.setdefault(tid, []).append(tg["Id"])

        sem = asyncio.Semaphore(10)

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
            # Filter out empty step lists
            all_steps = [s for s in all_steps if s]
            template_entry["steps"] = _aggregate_step_durations(all_steps)

    # Count total completed groups (those with valid DateActivated)
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
```

Also add the missing import at the top of the file:

```python
from datetime import datetime, timedelta, timezone
```

(Replace the existing `from datetime import datetime, timezone` import.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_analytics.py::TestGetTaskGroupCycleTimes::test_returns_cycle_times_by_template -v`
Expected: PASS

- [ ] **Step 5: Write test for `include_steps=True`**

Add to `TestGetTaskGroupCycleTimes` in `tests/test_analytics.py`:

```python
    @respx.mock
    @pytest.mark.asyncio
    async def test_includes_step_breakdown(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/taskgroups").mock(
            return_value=httpx.Response(200, json=[
                {
                    "Id": 1,
                    "DateActivated": "2026-01-01T00:00:00Z",
                    "DateCompleted": "2026-01-06T00:00:00Z",
                    "DateDue": "2026-01-10T00:00:00Z",
                    "Project": {
                        "ProjectTemplateId": 10,
                        "ProjectTemplate": {"Name": "DC Distribution Rqst"},
                    },
                },
            ])
        )
        respx.get("https://api.pensionpro.com/v2/taskgroups/1/tasks").mock(
            return_value=httpx.Response(200, json=[
                {
                    "Order": 1,
                    "TaskName": "Review",
                    "DateActivated": "2026-01-01T00:00:00Z",
                    "DateCompleted": "2026-01-03T00:00:00Z",
                },
                {
                    "Order": 2,
                    "TaskName": "Process",
                    "DateActivated": "2026-01-03T00:00:00Z",
                    "DateCompleted": "2026-01-06T00:00:00Z",
                },
            ])
        )

        result = await get_task_group_cycle_times(
            client, days_back=90, include_steps=True
        )

        dc = result["by_template"][0]
        assert "steps" in dc
        assert len(dc["steps"]) == 2
        assert dc["steps"][0]["task_name"] == "Review"
        assert dc["steps"][0]["avg_duration_days"] == 2.0
        assert dc["steps"][0]["is_bottleneck"] is False
        assert dc["steps"][1]["task_name"] == "Process"
        assert dc["steps"][1]["avg_duration_days"] == 3.0
        assert dc["steps"][1]["is_bottleneck"] is True
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_analytics.py::TestGetTaskGroupCycleTimes::test_includes_step_breakdown -v`
Expected: PASS

- [ ] **Step 7: Write test for optional filters**

Add to `TestGetTaskGroupCycleTimes` in `tests/test_analytics.py`:

```python
    @respx.mock
    @pytest.mark.asyncio
    async def test_applies_plan_and_template_filters(self, client: PensionProClient) -> None:
        route = respx.get("https://api.pensionpro.com/v2/taskgroups").mock(
            return_value=httpx.Response(200, json=[])
        )

        await get_task_group_cycle_times(
            client, days_back=30, plan_id=5, template_id=10
        )

        assert route.called
        url = str(route.calls[0].request.url)
        assert "Project/PlanId eq 5" in url
        assert "Project/ProjectTemplateId eq 10" in url
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/test_analytics.py::TestGetTaskGroupCycleTimes::test_applies_plan_and_template_filters -v`
Expected: PASS

- [ ] **Step 9: Write test for empty results**

Add to `TestGetTaskGroupCycleTimes` in `tests/test_analytics.py`:

```python
    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_results(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/taskgroups").mock(
            return_value=httpx.Response(200, json=[])
        )

        result = await get_task_group_cycle_times(client, days_back=90)

        assert result["by_template"] == []
        assert result["summary"]["total_groups_completed"] == 0
        assert result["summary"]["templates_analyzed"] == 0
```

- [ ] **Step 10: Run all integration tests**

Run: `uv run pytest tests/test_analytics.py::TestGetTaskGroupCycleTimes -v`
Expected: All PASS

- [ ] **Step 11: Commit**

```bash
git add src/pension_pro_mcp/tools/analytics.py tests/test_analytics.py
git commit -m "feat: add get_task_group_cycle_times with optional step analysis"
```

---

### Task 4: Register MCP tool in `server.py`

**Files:**
- Modify: `src/pension_pro_mcp/server.py`

- [ ] **Step 1: Add import**

Add to the imports section of `server.py` (after line 26):

```python
from pension_pro_mcp.tools.analytics import get_task_group_cycle_times
```

- [ ] **Step 2: Add tool registration**

Add after the worktray tools section (after the `_worktray_stats_resource` function, before the `# --- Swagger / API reference tools ---` comment):

```python

# --- Analytics tools ---


@mcp.tool(name="get_task_group_cycle_times")
@pipeline.wrap
async def _get_task_group_cycle_times(
    ctx: Context[ServerSession, AppContext],
    days_back: int = 90,
    plan_id: int | None = None,
    template_id: int | None = None,
    include_steps: bool = False,
) -> dict:
    """Compute task group cycle times segmented by project template.

    Analyzes completed task groups within the lookback window to reveal which
    workflows are slow and which steps are bottlenecks. Returns per-template
    stats including avg/median/min/max cycle time and SLA adherence.

    Set include_steps=true to fetch per-task step durations and identify the
    bottleneck step within each template. This makes additional API calls
    (one per task group) and may be slow for large result sets.
    """
    client = ctx.request_context.lifespan_context.client
    return await get_task_group_cycle_times(
        client,
        days_back=days_back,
        plan_id=plan_id,
        template_id=template_id,
        include_steps=include_steps,
    )
```

- [ ] **Step 3: Run full test suite to verify nothing is broken**

Run: `uv run pytest -v`
Expected: All tests pass (the pre-existing `test_projects.py` failure is unrelated)

- [ ] **Step 4: Commit**

```bash
git add src/pension_pro_mcp/server.py
git commit -m "feat: register get_task_group_cycle_times as MCP tool"
```
