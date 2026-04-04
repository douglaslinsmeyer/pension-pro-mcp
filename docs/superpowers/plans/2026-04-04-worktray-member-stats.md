# get_worktray_member_stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `get_worktray_member_stats` MCP tool that provides per-member workload, performance, and queue health metrics for a worktray.

**Architecture:** One tool function backed by three pure-function metric helpers (`_compute_workload_stats`, `_compute_performance_stats`, `_compute_queue_health`). Data fetching uses `asyncio.gather` for three concurrent API queries with OData `$expand` for rich context. Extends `build_odata_params` with `__ge`/`__le` operator support for date-range filtering.

**Tech Stack:** Python 3.12, httpx, pytest, pytest-asyncio, respx

**Spec:** `docs/superpowers/specs/2026-04-04-worktray-member-stats-design.md`

---

### Task 1: Extend `build_odata_params` with `__ge` and `__le` operators

**Files:**
- Modify: `src/pension_pro_mcp/client.py:83-96`
- Test: `tests/test_client.py`

- [ ] **Step 1: Write failing tests for `__ge` and `__le` suffixes**

Add two new test methods to the `TestODataQuery` class in `tests/test_client.py`:

```python
def test_builds_filter_with_ge(self, client: PensionProClient) -> None:
    params = client.build_odata_params(
        filters={"DateCompleted__ge": "2026-03-05T00:00:00Z"},
    )
    assert params["$filter"] == "DateCompleted ge 2026-03-05T00:00:00Z"

def test_builds_filter_with_le(self, client: PensionProClient) -> None:
    params = client.build_odata_params(
        filters={"DateCompleted__le": "2026-04-04T00:00:00Z"},
    )
    assert params["$filter"] == "DateCompleted le 2026-04-04T00:00:00Z"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_client.py::TestODataQuery::test_builds_filter_with_ge tests/test_client.py::TestODataQuery::test_builds_filter_with_le -v`
Expected: FAIL — `ge`/`le` suffixes not recognized, values get quoted as `eq` comparisons.

- [ ] **Step 3: Implement `__ge` and `__le` support in `build_odata_params`**

In `src/pension_pro_mcp/client.py`, replace the filter-building loop (lines 83-96) with:

```python
        if filters:
            clauses: list[str] = []
            for key, value in filters.items():
                escaped = value.replace("'", "''")
                if key.endswith("__contains"):
                    field = key[: -len("__contains")]
                    clauses.append(f"contains({field}, '{escaped}')")
                elif key.endswith("__ge"):
                    field = key[: -len("__ge")]
                    clauses.append(f"{field} ge {escaped}")
                elif key.endswith("__le"):
                    field = key[: -len("__le")]
                    clauses.append(f"{field} le {escaped}")
                elif value in ("true", "false", "null"):
                    clauses.append(f"{key} eq {value}")
                elif value.isdigit():
                    clauses.append(f"{key} eq {value}")
                else:
                    clauses.append(f"{key} eq '{escaped}'")
            params["$filter"] = " and ".join(clauses)
```

- [ ] **Step 4: Run all OData tests to verify pass and no regressions**

Run: `pytest tests/test_client.py::TestODataQuery -v`
Expected: All tests PASS including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add src/pension_pro_mcp/client.py tests/test_client.py
git commit -m "feat: add __ge and __le operator support to build_odata_params"
```

---

### Task 2: Implement `_compute_workload_stats` helper

**Files:**
- Modify: `src/pension_pro_mcp/tools/worktrays.py`
- Test: `tests/test_worktrays.py`

- [ ] **Step 1: Write failing tests for `_compute_workload_stats`**

Add a new test class to `tests/test_worktrays.py`:

```python
from pension_pro_mcp.tools.worktrays import _compute_workload_stats


class TestComputeWorkloadStats:
    def test_counts_active_tasks_per_member(self) -> None:
        members = [
            {"contactID": 1, "RoleID": 10, "Contact": {"FirstName": "Alice", "LastName": "Smith"}},
            {"contactID": 2, "RoleID": 20, "Contact": {"FirstName": "Bob", "LastName": "Jones"}},
        ]
        active_tasks = [
            {
                "Id": 100, "TaskName": "Review", "AssignedToId": 1,
                "TaskActive": "2026-03-30T00:00:00Z", "DateAdded": "2026-03-28T00:00:00Z",
                "TaskGroup": {"Name": "Group A", "Project": {"Name": "Annual Val", "Id": 50}},
            },
            {
                "Id": 101, "TaskName": "Filing", "AssignedToId": 1,
                "TaskActive": "2026-04-01T00:00:00Z", "DateAdded": "2026-03-29T00:00:00Z",
                "TaskGroup": {"Name": "Group B", "Project": {"Name": "5500 Filing", "Id": 51}},
            },
            {
                "Id": 102, "TaskName": "Review", "AssignedToId": None,
                "TaskActive": None, "DateAdded": "2026-04-02T00:00:00Z",
                "TaskGroup": {"Name": "Group A", "Project": {"Name": "Annual Val", "Id": 50}},
            },
        ]
        result = _compute_workload_stats(active_tasks, members)
        alice = next(m for m in result["members"] if m["contact_id"] == 1)
        assert alice["workload"]["active_task_count"] == 2
        assert len(alice["workload"]["tasks"]) == 2
        bob = next(m for m in result["members"] if m["contact_id"] == 2)
        assert bob["workload"]["active_task_count"] == 0
        assert result["aggregate"]["total_active"] == 3
        assert result["aggregate"]["unassigned_count"] == 1

    def test_empty_worktray(self) -> None:
        members = [
            {"contactID": 1, "RoleID": 10, "Contact": {"FirstName": "Alice", "LastName": "Smith"}},
        ]
        result = _compute_workload_stats([], members)
        alice = next(m for m in result["members"] if m["contact_id"] == 1)
        assert alice["workload"]["active_task_count"] == 0
        assert result["aggregate"]["total_active"] == 0
        assert result["aggregate"]["unassigned_count"] == 0

    def test_task_age_uses_task_active_over_date_added(self) -> None:
        members = [
            {"contactID": 1, "RoleID": 10, "Contact": {"FirstName": "A", "LastName": "B"}},
        ]
        active_tasks = [
            {
                "Id": 100, "TaskName": "Review", "AssignedToId": 1,
                "TaskActive": "2026-04-02T00:00:00Z", "DateAdded": "2026-03-01T00:00:00Z",
                "TaskGroup": {"Name": "G", "Project": {"Name": "P", "Id": 1}},
            },
        ]
        result = _compute_workload_stats(active_tasks, members, now=datetime(2026, 4, 4, tzinfo=timezone.utc))
        task = result["members"][0]["workload"]["tasks"][0]
        assert task["age_days"] == 2  # from TaskActive, not DateAdded
```

Also add imports at the top of the test file:

```python
from datetime import datetime, timezone
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_worktrays.py::TestComputeWorkloadStats -v`
Expected: FAIL — `_compute_workload_stats` not defined.

- [ ] **Step 3: Implement `_compute_workload_stats`**

Add to `src/pension_pro_mcp/tools/worktrays.py`, after the existing imports (note: `Counter` is already imported at the top of the file):

```python
from collections import defaultdict
from datetime import datetime, timedelta, timezone


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_worktrays.py::TestComputeWorkloadStats -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pension_pro_mcp/tools/worktrays.py tests/test_worktrays.py
git commit -m "feat: add _compute_workload_stats helper for worktray analytics"
```

---

### Task 3: Implement `_compute_performance_stats` helper

**Files:**
- Modify: `src/pension_pro_mcp/tools/worktrays.py`
- Test: `tests/test_worktrays.py`

- [ ] **Step 1: Write failing tests for `_compute_performance_stats`**

Add to `tests/test_worktrays.py`:

```python
from pension_pro_mcp.tools.worktrays import _compute_performance_stats


class TestComputePerformanceStats:
    def test_computes_per_member_metrics(self) -> None:
        members = [
            {"contactID": 1, "RoleID": 10, "Contact": {"FirstName": "Alice", "LastName": "Smith"}},
            {"contactID": 2, "RoleID": 20, "Contact": {"FirstName": "Bob", "LastName": "Jones"}},
        ]
        completed_tasks = [
            {
                "Id": 100, "TaskName": "Review", "AssignedToId": 1,
                "TaskActive": "2026-03-01T00:00:00Z",
                "DateCompleted": "2026-03-02T00:00:00Z",
                "AcknowledgeDate": "2026-03-01T02:00:00Z",
                "Rejections": 0,
            },
            {
                "Id": 101, "TaskName": "Review", "AssignedToId": 1,
                "TaskActive": "2026-03-05T00:00:00Z",
                "DateCompleted": "2026-03-05T12:00:00Z",
                "AcknowledgeDate": "2026-03-05T01:00:00Z",
                "Rejections": 1,
            },
            {
                "Id": 102, "TaskName": "Filing", "AssignedToId": 2,
                "TaskActive": "2026-03-10T00:00:00Z",
                "DateCompleted": "2026-03-12T00:00:00Z",
                "AcknowledgeDate": None,
                "Rejections": 0,
            },
        ]
        result = _compute_performance_stats(completed_tasks, members)
        alice = next(m for m in result["members"] if m["contact_id"] == 1)
        assert alice["performance"]["tasks_completed"] == 2
        # Task 100: 24h, Task 101: 12h -> avg 18h
        assert alice["performance"]["avg_completion_hours"] == 18.0
        # Task 100: 2h, Task 101: 1h -> avg 1.5h
        assert alice["performance"]["avg_pickup_hours"] == 1.5
        # 1 rejection / 2 tasks = 0.5
        assert alice["performance"]["rejection_rate"] == 0.5
        assert alice["performance"]["task_type_breakdown"] == [{"task_name": "Review", "count": 2}]

        bob = next(m for m in result["members"] if m["contact_id"] == 2)
        assert bob["performance"]["tasks_completed"] == 1
        assert bob["performance"]["avg_pickup_hours"] is None  # no acknowledge dates

        assert result["aggregate"]["total_completed"] == 3

    def test_member_with_zero_completions(self) -> None:
        members = [
            {"contactID": 1, "RoleID": 10, "Contact": {"FirstName": "Alice", "LastName": "Smith"}},
        ]
        result = _compute_performance_stats([], members)
        alice = result["members"][0]
        assert alice["performance"]["tasks_completed"] == 0
        assert alice["performance"]["avg_completion_hours"] is None
        assert alice["performance"]["avg_pickup_hours"] is None
        assert alice["performance"]["rejection_rate"] == 0.0
        assert alice["performance"]["task_type_breakdown"] == []
        assert result["aggregate"]["total_completed"] == 0
        assert result["aggregate"]["team_avg_completion_hours"] is None

    def test_tasks_with_missing_task_active(self) -> None:
        members = [
            {"contactID": 1, "RoleID": 10, "Contact": {"FirstName": "A", "LastName": "B"}},
        ]
        completed_tasks = [
            {
                "Id": 100, "TaskName": "Review", "AssignedToId": 1,
                "TaskActive": None,
                "DateCompleted": "2026-03-02T00:00:00Z",
                "AcknowledgeDate": None,
                "Rejections": 0,
            },
        ]
        result = _compute_performance_stats(completed_tasks, members)
        alice = result["members"][0]
        assert alice["performance"]["tasks_completed"] == 1
        assert alice["performance"]["avg_completion_hours"] is None  # can't compute without TaskActive
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_worktrays.py::TestComputePerformanceStats -v`
Expected: FAIL — `_compute_performance_stats` not defined.

- [ ] **Step 3: Implement `_compute_performance_stats`**

Add to `src/pension_pro_mcp/tools/worktrays.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_worktrays.py::TestComputePerformanceStats -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pension_pro_mcp/tools/worktrays.py tests/test_worktrays.py
git commit -m "feat: add _compute_performance_stats helper for worktray analytics"
```

---

### Task 4: Implement `_compute_queue_health` helper

**Files:**
- Modify: `src/pension_pro_mcp/tools/worktrays.py`
- Test: `tests/test_worktrays.py`

- [ ] **Step 1: Write failing tests for `_compute_queue_health`**

Add to `tests/test_worktrays.py`:

```python
from pension_pro_mcp.tools.worktrays import _compute_queue_health


class TestComputeQueueHealth:
    def test_computes_throughput_and_intake(self) -> None:
        now = datetime(2026, 4, 4, tzinfo=timezone.utc)
        completed_tasks = [
            {"Id": 1, "DateAdded": "2026-03-10T00:00:00Z", "DateCompleted": "2026-03-15T00:00:00Z"},
            {"Id": 2, "DateAdded": "2026-03-20T00:00:00Z", "DateCompleted": "2026-03-25T00:00:00Z"},
        ]
        active_tasks = [
            {
                "Id": 3, "DateAdded": "2026-03-28T00:00:00Z",
                "TaskActive": "2026-03-30T00:00:00Z", "DaysToComp": 3,
            },
            {
                "Id": 4, "DateAdded": "2026-02-01T00:00:00Z",  # added before window
                "TaskActive": "2026-02-05T00:00:00Z", "DaysToComp": 5,
            },
        ]
        result = _compute_queue_health(active_tasks, completed_tasks, days_back=30, now=now)
        assert result["throughput_per_day"] == round(2 / 30, 2)
        # 3 tasks added within window (ids 1, 2, 3); id 4 added before window
        assert result["intake_per_day"] == round(3 / 30, 2)
        assert result["queue_growing"] is True

    def test_detects_overdue_tasks(self) -> None:
        now = datetime(2026, 4, 4, tzinfo=timezone.utc)
        active_tasks = [
            {
                "Id": 10, "TaskName": "Slow Task", "DaysToComp": 3,
                "TaskActive": "2026-03-20T00:00:00Z", "DateAdded": "2026-03-18T00:00:00Z",
                "TaskGroup": {"Name": "G", "Project": {"Name": "Proj A", "Id": 1}},
            },
            {
                "Id": 11, "TaskName": "OK Task", "DaysToComp": 30,
                "TaskActive": "2026-04-01T00:00:00Z", "DateAdded": "2026-04-01T00:00:00Z",
                "TaskGroup": {"Name": "G", "Project": {"Name": "Proj B", "Id": 2}},
            },
            {
                "Id": 12, "TaskName": "No SLA", "DaysToComp": None,
                "TaskActive": "2026-03-01T00:00:00Z", "DateAdded": "2026-03-01T00:00:00Z",
                "TaskGroup": None,
            },
        ]
        result = _compute_queue_health(active_tasks, [], days_back=30, now=now)
        assert result["overdue_count"] == 1
        assert result["overdue_tasks"][0]["task_id"] == 10
        assert result["overdue_tasks"][0]["project"] == "Proj A"
        assert result["oldest_active_task_age_days"] == 34  # from task 12: Mar 1 -> Apr 4

    def test_empty_worktray(self) -> None:
        now = datetime(2026, 4, 4, tzinfo=timezone.utc)
        result = _compute_queue_health([], [], days_back=30, now=now)
        assert result["throughput_per_day"] == 0.0
        assert result["intake_per_day"] == 0.0
        assert result["queue_growing"] is False
        assert result["oldest_active_task_age_days"] == 0
        assert result["overdue_count"] == 0
        assert result["overdue_tasks"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_worktrays.py::TestComputeQueueHealth -v`
Expected: FAIL — `_compute_queue_health` not defined.

- [ ] **Step 3: Implement `_compute_queue_health`**

Add to `src/pension_pro_mcp/tools/worktrays.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_worktrays.py::TestComputeQueueHealth -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pension_pro_mcp/tools/worktrays.py tests/test_worktrays.py
git commit -m "feat: add _compute_queue_health helper for worktray analytics"
```

---

### Task 5: Implement `get_worktray_member_stats` tool function

**Files:**
- Modify: `src/pension_pro_mcp/tools/worktrays.py`
- Test: `tests/test_worktrays.py`

- [ ] **Step 1: Write failing integration test**

Add to `tests/test_worktrays.py`:

```python
from pension_pro_mcp.tools.worktrays import get_worktray_member_stats


class TestGetWorktrayMemberStats:
    @respx.mock
    @pytest.mark.asyncio
    async def test_assembles_full_response(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/worktrayMembers").mock(
            return_value=httpx.Response(200, json=[
                {"Id": 1, "contactID": 500, "WorktrayID": 100, "RoleID": 1, "Contact": {"FirstName": "Alice", "LastName": "Smith"}},
                {"Id": 2, "contactID": 501, "WorktrayID": 100, "RoleID": 2, "Contact": {"FirstName": "Bob", "LastName": "Jones"}},
                {"Id": 3, "contactID": 600, "WorktrayID": 999, "RoleID": 1, "Contact": {"FirstName": "Other", "LastName": "Person"}},
            ])
        )
        # Active tasks route — matches filter with DateCompleted eq null
        respx.get("https://api.pensionpro.com/v2/tasks").mock(
            side_effect=lambda request: httpx.Response(200, json=[
                {
                    "Id": 10, "TaskName": "Review", "AssignedToId": 500,
                    "TaskActive": "2026-04-01T00:00:00Z", "DateAdded": "2026-03-28T00:00:00Z",
                    "DateCompleted": None, "AcknowledgeDate": None,
                    "DaysToComp": 5, "Rejections": 0,
                    "TaskGroup": {"Name": "G1", "Project": {"Name": "Annual Val", "Id": 50}},
                },
            ]) if "null" in str(request.url) else httpx.Response(200, json=[
                {
                    "Id": 20, "TaskName": "Review", "AssignedToId": 500,
                    "TaskActive": "2026-03-10T00:00:00Z", "DateAdded": "2026-03-08T00:00:00Z",
                    "DateCompleted": "2026-03-11T12:00:00Z", "AcknowledgeDate": "2026-03-10T01:00:00Z",
                    "DaysToComp": 5, "Rejections": 0,
                    "TaskGroup": {"Name": "G1", "Project": {"Name": "Annual Val", "Id": 50}},
                },
            ])
        )

        result = await get_worktray_member_stats(client, worktray_id=100, days_back=30)

        assert result["worktray_id"] == 100
        assert result["period_days"] == 30
        assert len(result["members"]) == 2
        alice = next(m for m in result["members"] if m["contact_id"] == 500)
        assert alice["name"] == "Alice Smith"
        assert alice["workload"]["active_task_count"] == 1
        assert alice["performance"]["tasks_completed"] == 1
        assert result["aggregate"]["workload"]["total_active"] == 1
        assert result["aggregate"]["performance"]["total_completed"] == 1
        assert "throughput_per_day" in result["aggregate"]["queue_health"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_empty_worktray(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/worktrayMembers").mock(
            return_value=httpx.Response(200, json=[])
        )
        respx.get("https://api.pensionpro.com/v2/tasks").mock(
            return_value=httpx.Response(200, json=[])
        )

        result = await get_worktray_member_stats(client, worktray_id=100, days_back=30)

        assert result["members"] == []
        assert result["aggregate"]["workload"]["total_active"] == 0
        assert result["aggregate"]["performance"]["total_completed"] == 0
        assert result["aggregate"]["queue_health"]["throughput_per_day"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_worktrays.py::TestGetWorktrayMemberStats -v`
Expected: FAIL — `get_worktray_member_stats` not defined.

- [ ] **Step 3: Implement `get_worktray_member_stats`**

Add to `src/pension_pro_mcp/tools/worktrays.py`:

```python
import asyncio


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_worktrays.py::TestGetWorktrayMemberStats -v`
Expected: All 2 tests PASS.

- [ ] **Step 5: Run all worktray tests to check for regressions**

Run: `pytest tests/test_worktrays.py -v`
Expected: All tests PASS (existing + new).

- [ ] **Step 6: Commit**

```bash
git add src/pension_pro_mcp/tools/worktrays.py tests/test_worktrays.py
git commit -m "feat: add get_worktray_member_stats tool function"
```

---

### Task 6: Register MCP tool in server.py

**Files:**
- Modify: `src/pension_pro_mcp/server.py:26,449`

- [ ] **Step 1: Update import**

In `src/pension_pro_mcp/server.py`, change line 26 from:

```python
from pension_pro_mcp.tools.worktrays import get_worktrays, get_worktray
```

to:

```python
from pension_pro_mcp.tools.worktrays import get_worktrays, get_worktray, get_worktray_member_stats
```

- [ ] **Step 2: Add tool registration**

After the `_get_worktray` tool (after line 449), add:

```python


@mcp.tool(name="get_worktray_member_stats")
@pipeline.wrap
async def _get_worktray_member_stats(
    ctx: Context[ServerSession, AppContext],
    worktray_id: int,
    days_back: int = 30,
) -> dict:
    """Get per-member workload, performance, and queue health metrics for a worktray.

    Analyzes completed tasks within the lookback window and current active tasks.
    Returns per-member stats (task counts, avg completion time, pickup time, rejection rate)
    plus aggregate queue health (throughput, intake rate, overdue tasks).
    """
    client = ctx.request_context.lifespan_context.client
    return await get_worktray_member_stats(client, worktray_id=worktray_id, days_back=days_back)
```

- [ ] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/pension_pro_mcp/server.py
git commit -m "feat: register get_worktray_member_stats as MCP tool"
```

---

### Task 7: Final verification

- [ ] **Step 1: Run full test suite one final time**

Run: `pytest -v`
Expected: All tests PASS.

- [ ] **Step 2: Verify the tool module imports cleanly**

Run: `python -c "from pension_pro_mcp.tools.worktrays import get_worktray_member_stats; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify the server module imports cleanly**

Run: `python -c "from pension_pro_mcp.server import mcp; print(f'{len(mcp._tool_manager._tools)} tools registered')"`
Expected: prints tool count (should be 27, up from 26).
