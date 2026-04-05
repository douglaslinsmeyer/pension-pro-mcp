# Employee Stats Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `get_employee_stats(name, days_back=30)` tool that provides per-employee performance analysis across all worktrays, segmented by worktray ID.

**Architecture:** Search employees by last name, resolve to a single contact, then fetch their worktray memberships and tasks (completed + active) in parallel. Group tasks by `TeamId` to produce per-worktray segments with workload, throughput, and quality metrics. Cache full results, return compact summary.

**Tech Stack:** Python, pytest, respx, httpx, asyncio, FastMCP

---

### Task 1: Employee Name Resolution

**Files:**
- Modify: `src/pension_pro_mcp/tools/worktrays.py` (add `_resolve_employee`)
- Test: `tests/test_worktrays.py` (add `TestResolveEmployee`)

- [ ] **Step 1: Write the failing tests for `_resolve_employee`**

Add to `tests/test_worktrays.py`:

```python
from pension_pro_mcp.tools.worktrays import _resolve_employee


class TestResolveEmployee:
    @respx.mock
    @pytest.mark.asyncio
    async def test_single_match(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/contacts").mock(
            return_value=httpx.Response(200, json=[
                {
                    "Id": 500, "FirstName": "Alice", "LastName": "Smith",
                    "SystemEmployee": True,
                    "Employee": {"Id": 50, "Active": True, "ContactId": 500},
                },
            ])
        )
        result = await _resolve_employee(client, "Smith")
        assert result["status"] == "found"
        assert result["contact_id"] == 500
        assert result["name"] == "Alice Smith"

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_matches(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/contacts").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await _resolve_employee(client, "Nobody")
        assert result["status"] == "not_found"

    @respx.mock
    @pytest.mark.asyncio
    async def test_multiple_matches(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/contacts").mock(
            return_value=httpx.Response(200, json=[
                {
                    "Id": 500, "FirstName": "Alice", "LastName": "Smith",
                    "SystemEmployee": True,
                    "Employee": {"Id": 50, "Active": True, "ContactId": 500},
                },
                {
                    "Id": 501, "FirstName": "Bob", "LastName": "Smithson",
                    "SystemEmployee": True,
                    "Employee": {"Id": 51, "Active": True, "ContactId": 501},
                },
            ])
        )
        result = await _resolve_employee(client, "Smith")
        assert result["status"] == "ambiguous"
        assert len(result["candidates"]) == 2
        assert result["candidates"][0]["contact_id"] == 500
        assert result["candidates"][0]["name"] == "Alice Smith"

    @respx.mock
    @pytest.mark.asyncio
    async def test_filters_inactive_employees(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/contacts").mock(
            return_value=httpx.Response(200, json=[
                {
                    "Id": 500, "FirstName": "Alice", "LastName": "Smith",
                    "SystemEmployee": True,
                    "Employee": {"Id": 50, "Active": True, "ContactId": 500},
                },
                {
                    "Id": 501, "FirstName": "Bob", "LastName": "Smith",
                    "SystemEmployee": True,
                    "Employee": {"Id": 51, "Active": False, "ContactId": 501},
                },
            ])
        )
        result = await _resolve_employee(client, "Smith")
        assert result["status"] == "found"
        assert result["contact_id"] == 500

    @respx.mock
    @pytest.mark.asyncio
    async def test_filters_non_employees(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/contacts").mock(
            return_value=httpx.Response(200, json=[
                {
                    "Id": 500, "FirstName": "Alice", "LastName": "Smith",
                    "SystemEmployee": True,
                    "Employee": {"Id": 50, "Active": True, "ContactId": 500},
                },
                {
                    "Id": 502, "FirstName": "Carol", "LastName": "Smith",
                    "SystemEmployee": False,
                    "Employee": None,
                },
            ])
        )
        result = await _resolve_employee(client, "Smith")
        assert result["status"] == "found"
        assert result["contact_id"] == 500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_worktrays.py::TestResolveEmployee -v`
Expected: FAIL with `ImportError: cannot import name '_resolve_employee'`

- [ ] **Step 3: Implement `_resolve_employee`**

Add to `src/pension_pro_mcp/tools/worktrays.py` after the existing helper functions (after `_task_project_name`):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_worktrays.py::TestResolveEmployee -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pension_pro_mcp/tools/worktrays.py tests/test_worktrays.py
git commit -m "feat: add _resolve_employee helper for name-based employee lookup"
```

---

### Task 2: Per-Segment Workload Computation

**Files:**
- Modify: `src/pension_pro_mcp/tools/worktrays.py` (add `_compute_employee_workload`)
- Test: `tests/test_worktrays.py` (add `TestComputeEmployeeWorkload`)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_worktrays.py`:

```python
from pension_pro_mcp.tools.worktrays import _compute_employee_workload


class TestComputeEmployeeWorkload:
    def test_counts_active_tasks(self) -> None:
        now = datetime(2026, 4, 4, tzinfo=timezone.utc)
        active_tasks = [
            {
                "Id": 100, "TaskName": "Review",
                "TaskActive": "2026-03-30T00:00:00Z", "DateAdded": "2026-03-28T00:00:00Z",
                "TaskGroup": {"Name": "G1", "Project": {"Name": "Annual Val", "Id": 50}},
            },
            {
                "Id": 101, "TaskName": "Filing",
                "TaskActive": "2026-04-01T00:00:00Z", "DateAdded": "2026-03-29T00:00:00Z",
                "TaskGroup": {"Name": "G2", "Project": {"Name": "5500 Filing", "Id": 51}},
            },
        ]
        result = _compute_employee_workload(active_tasks, now=now)
        assert result["active_task_count"] == 2
        assert result["oldest_task_age_days"] == 5  # Mar 30 -> Apr 4

    def test_empty_tasks(self) -> None:
        now = datetime(2026, 4, 4, tzinfo=timezone.utc)
        result = _compute_employee_workload([], now=now)
        assert result["active_task_count"] == 0
        assert result["oldest_task_age_days"] == 0

    def test_includes_task_details(self) -> None:
        now = datetime(2026, 4, 4, tzinfo=timezone.utc)
        active_tasks = [
            {
                "Id": 100, "TaskName": "Review",
                "TaskActive": "2026-04-02T00:00:00Z", "DateAdded": "2026-04-01T00:00:00Z",
                "TaskGroup": {"Name": "G1", "Project": {"Name": "Annual Val", "Id": 50}},
            },
        ]
        result = _compute_employee_workload(active_tasks, now=now)
        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["task_name"] == "Review"
        assert result["tasks"][0]["project"] == "Annual Val"
        assert result["tasks"][0]["age_days"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_worktrays.py::TestComputeEmployeeWorkload -v`
Expected: FAIL with `ImportError: cannot import name '_compute_employee_workload'`

- [ ] **Step 3: Implement `_compute_employee_workload`**

Add to `src/pension_pro_mcp/tools/worktrays.py` after `_resolve_employee`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_worktrays.py::TestComputeEmployeeWorkload -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pension_pro_mcp/tools/worktrays.py tests/test_worktrays.py
git commit -m "feat: add _compute_employee_workload for per-segment active task metrics"
```

---

### Task 3: Per-Segment Throughput Computation

**Files:**
- Modify: `src/pension_pro_mcp/tools/worktrays.py` (add `_compute_employee_throughput`)
- Test: `tests/test_worktrays.py` (add `TestComputeEmployeeThroughput`)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_worktrays.py`:

```python
from pension_pro_mcp.tools.worktrays import _compute_employee_throughput


class TestComputeEmployeeThroughput:
    def test_computes_throughput_metrics(self) -> None:
        completed_tasks = [
            {
                "Id": 100, "TaskName": "Review", "AssignedToId": 500,
                "TaskActive": "2026-03-01T00:00:00Z",
                "DateCompleted": "2026-03-02T00:00:00Z",
                "AcknowledgeDate": "2026-03-01T02:00:00Z",
                "Rejections": 0, "Rejected": False,
                "TaskGroup": {"Name": "G1", "Project": {"Name": "Annual Val", "Id": 50}},
            },
            {
                "Id": 101, "TaskName": "Filing", "AssignedToId": 500,
                "TaskActive": "2026-03-05T00:00:00Z",
                "DateCompleted": "2026-03-05T12:00:00Z",
                "AcknowledgeDate": "2026-03-05T01:00:00Z",
                "Rejections": 0, "Rejected": False,
                "TaskGroup": {"Name": "G2", "Project": {"Name": "5500 Filing", "Id": 51}},
            },
        ]
        result = _compute_employee_throughput(completed_tasks, days_back=30)
        assert result["tasks_completed"] == 2
        # Task 100: 24h, Task 101: 12h -> avg 18h
        assert result["avg_completion_hours"] == 18.0
        # Task 100: 2h, Task 101: 1h -> avg 1.5h
        assert result["avg_pickup_hours"] == 1.5
        assert result["tasks_per_day"] == round(2 / 30, 2)

    def test_empty_tasks(self) -> None:
        result = _compute_employee_throughput([], days_back=30)
        assert result["tasks_completed"] == 0
        assert result["avg_completion_hours"] is None
        assert result["avg_pickup_hours"] is None
        assert result["tasks_per_day"] == 0.0

    def test_missing_task_active(self) -> None:
        completed_tasks = [
            {
                "Id": 100, "TaskName": "Review", "AssignedToId": 500,
                "TaskActive": None,
                "DateCompleted": "2026-03-02T00:00:00Z",
                "AcknowledgeDate": None,
                "Rejections": 0, "Rejected": False,
                "TaskGroup": {"Name": "G1", "Project": {"Name": "Annual Val", "Id": 50}},
            },
        ]
        result = _compute_employee_throughput(completed_tasks, days_back=30)
        assert result["tasks_completed"] == 1
        assert result["avg_completion_hours"] is None
        assert result["avg_pickup_hours"] is None

    def test_includes_task_type_and_project_breakdowns(self) -> None:
        completed_tasks = [
            {
                "Id": 100, "TaskName": "Review", "AssignedToId": 500,
                "TaskActive": "2026-03-01T00:00:00Z",
                "DateCompleted": "2026-03-02T00:00:00Z",
                "AcknowledgeDate": None, "Rejections": 0, "Rejected": False,
                "TaskGroup": {"Name": "G1", "Project": {"Name": "Annual Val", "Id": 50}},
            },
            {
                "Id": 101, "TaskName": "Review", "AssignedToId": 500,
                "TaskActive": "2026-03-05T00:00:00Z",
                "DateCompleted": "2026-03-06T00:00:00Z",
                "AcknowledgeDate": None, "Rejections": 0, "Rejected": False,
                "TaskGroup": {"Name": "G2", "Project": {"Name": "Annual Val", "Id": 50}},
            },
            {
                "Id": 102, "TaskName": "Filing", "AssignedToId": 500,
                "TaskActive": "2026-03-10T00:00:00Z",
                "DateCompleted": "2026-03-10T06:00:00Z",
                "AcknowledgeDate": None, "Rejections": 0, "Rejected": False,
                "TaskGroup": {"Name": "G3", "Project": {"Name": "5500 Filing", "Id": 51}},
            },
        ]
        result = _compute_employee_throughput(completed_tasks, days_back=30)
        assert result["task_type_breakdown"] == [
            {"task_name": "Review", "count": 2},
            {"task_name": "Filing", "count": 1},
        ]
        assert len(result["by_project"]) == 2
        annual = next(p for p in result["by_project"] if p["project"] == "Annual Val")
        assert annual["tasks_completed"] == 2
        assert annual["avg_completion_hours"] == 24.0  # both 24h
        filing = next(p for p in result["by_project"] if p["project"] == "5500 Filing")
        assert filing["tasks_completed"] == 1
        assert filing["avg_completion_hours"] == 6.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_worktrays.py::TestComputeEmployeeThroughput -v`
Expected: FAIL with `ImportError: cannot import name '_compute_employee_throughput'`

- [ ] **Step 3: Implement `_compute_employee_throughput`**

Add to `src/pension_pro_mcp/tools/worktrays.py` after `_compute_employee_workload`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_worktrays.py::TestComputeEmployeeThroughput -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pension_pro_mcp/tools/worktrays.py tests/test_worktrays.py
git commit -m "feat: add _compute_employee_throughput for per-segment completion metrics"
```

---

### Task 4: Per-Segment Quality Computation

**Files:**
- Modify: `src/pension_pro_mcp/tools/worktrays.py` (add `_compute_employee_quality`)
- Test: `tests/test_worktrays.py` (add `TestComputeEmployeeQuality`)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_worktrays.py`:

```python
from pension_pro_mcp.tools.worktrays import _compute_employee_quality


class TestComputeEmployeeQuality:
    def test_computes_rejection_and_bounce_back_rates(self) -> None:
        completed_tasks = [
            {"Id": 100, "Rejections": 1, "Rejected": False},
            {"Id": 101, "Rejections": 0, "Rejected": True},
            {"Id": 102, "Rejections": 0, "Rejected": False},
            {"Id": 103, "Rejections": 2, "Rejected": True},
        ]
        result = _compute_employee_quality(completed_tasks)
        # 2 tasks with Rejections > 0 out of 4
        assert result["rejection_rate"] == 0.5
        assert result["total_rejections"] == 3
        # 2 tasks with Rejected == True out of 4
        assert result["bounce_back_count"] == 2
        assert result["bounce_back_rate"] == 0.5

    def test_empty_tasks(self) -> None:
        result = _compute_employee_quality([])
        assert result["rejection_rate"] == 0.0
        assert result["total_rejections"] == 0
        assert result["bounce_back_count"] == 0
        assert result["bounce_back_rate"] == 0.0

    def test_no_rejections_or_bounce_backs(self) -> None:
        completed_tasks = [
            {"Id": 100, "Rejections": 0, "Rejected": False},
            {"Id": 101, "Rejections": 0, "Rejected": False},
        ]
        result = _compute_employee_quality(completed_tasks)
        assert result["rejection_rate"] == 0.0
        assert result["total_rejections"] == 0
        assert result["bounce_back_count"] == 0
        assert result["bounce_back_rate"] == 0.0

    def test_handles_none_values(self) -> None:
        completed_tasks = [
            {"Id": 100, "Rejections": None, "Rejected": None},
            {"Id": 101, "Rejections": 1, "Rejected": True},
        ]
        result = _compute_employee_quality(completed_tasks)
        assert result["rejection_rate"] == 0.5
        assert result["total_rejections"] == 1
        assert result["bounce_back_count"] == 1
        assert result["bounce_back_rate"] == 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_worktrays.py::TestComputeEmployeeQuality -v`
Expected: FAIL with `ImportError: cannot import name '_compute_employee_quality'`

- [ ] **Step 3: Implement `_compute_employee_quality`**

Add to `src/pension_pro_mcp/tools/worktrays.py` after `_compute_employee_throughput`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_worktrays.py::TestComputeEmployeeQuality -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pension_pro_mcp/tools/worktrays.py tests/test_worktrays.py
git commit -m "feat: add _compute_employee_quality for rejection and bounce-back metrics"
```

---

### Task 5: Compact Employee Segment Helper

**Files:**
- Modify: `src/pension_pro_mcp/tools/worktrays.py` (add `_compact_employee_segment`)
- Test: `tests/test_worktrays.py` (add `TestCompactEmployeeSegment`)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_worktrays.py`:

```python
from pension_pro_mcp.tools.worktrays import _compact_employee_segment


class TestCompactEmployeeSegment:
    def test_strips_detail_fields(self) -> None:
        segment = {
            "worktray_id": 10,
            "worktray_name": "Compliance",
            "workload": {
                "active_task_count": 3,
                "oldest_task_age_days": 5,
                "tasks": [{"task_name": "Review", "project": "Proj A", "age_days": 5}],
            },
            "throughput": {
                "tasks_completed": 10,
                "avg_completion_hours": 18.0,
                "avg_pickup_hours": 2.0,
                "tasks_per_day": 0.33,
                "task_type_breakdown": [{"task_name": "Review", "count": 10}],
                "by_project": [{"project": "Proj A", "tasks_completed": 10}],
            },
            "quality": {
                "rejection_rate": 0.1,
                "total_rejections": 1,
                "bounce_back_count": 2,
                "bounce_back_rate": 0.2,
            },
        }
        result = _compact_employee_segment(segment)
        # Workload: tasks list stripped
        assert "tasks" not in result["workload"]
        assert result["workload"]["active_task_count"] == 3
        assert result["workload"]["oldest_task_age_days"] == 5
        # Throughput: task_type_breakdown and by_project stripped
        assert "task_type_breakdown" not in result["throughput"]
        assert "by_project" not in result["throughput"]
        assert result["throughput"]["tasks_completed"] == 10
        assert result["throughput"]["avg_completion_hours"] == 18.0
        # Quality: unchanged
        assert result["quality"]["rejection_rate"] == 0.1
        assert result["quality"]["bounce_back_count"] == 2
        # Identity fields preserved
        assert result["worktray_id"] == 10
        assert result["worktray_name"] == "Compliance"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_worktrays.py::TestCompactEmployeeSegment -v`
Expected: FAIL with `ImportError: cannot import name '_compact_employee_segment'`

- [ ] **Step 3: Implement `_compact_employee_segment`**

Add to `src/pension_pro_mcp/tools/worktrays.py` after `_compute_employee_quality`:

```python
def _compact_employee_segment(segment: dict[str, Any]) -> dict[str, Any]:
    """Strip detail fields from a worktray segment for the compact summary."""
    return {
        "worktray_id": segment["worktray_id"],
        "worktray_name": segment.get("worktray_name"),
        "workload": {
            k: v for k, v in segment["workload"].items()
            if k != "tasks"
        },
        "throughput": {
            k: v for k, v in segment["throughput"].items()
            if k not in ("task_type_breakdown", "by_project")
        },
        "quality": segment["quality"],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_worktrays.py::TestCompactEmployeeSegment -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pension_pro_mcp/tools/worktrays.py tests/test_worktrays.py
git commit -m "feat: add _compact_employee_segment for stripping detail from segments"
```

---

### Task 6: Main `get_employee_stats` Tool Function

**Files:**
- Modify: `src/pension_pro_mcp/tools/worktrays.py` (add `get_employee_stats`, `read_cached_employee_stats`)
- Test: `tests/test_worktrays.py` (add `TestGetEmployeeStats`)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_worktrays.py`:

```python
from pension_pro_mcp.tools.worktrays import get_employee_stats


class TestGetEmployeeStats:
    @respx.mock
    @pytest.mark.asyncio
    async def test_not_found(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/contacts").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await get_employee_stats(client, name="Nobody")
        assert result["status"] == "not_found"

    @respx.mock
    @pytest.mark.asyncio
    async def test_ambiguous(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/contacts").mock(
            return_value=httpx.Response(200, json=[
                {
                    "Id": 500, "FirstName": "Alice", "LastName": "Smith",
                    "SystemEmployee": True,
                    "Employee": {"Id": 50, "Active": True, "ContactId": 500},
                },
                {
                    "Id": 501, "FirstName": "Bob", "LastName": "Smithson",
                    "SystemEmployee": True,
                    "Employee": {"Id": 51, "Active": True, "ContactId": 501},
                },
            ])
        )
        result = await get_employee_stats(client, name="Smith")
        assert result["status"] == "ambiguous"
        assert len(result["candidates"]) == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_assembles_full_response(self, client: PensionProClient, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

        # Mock contact search
        respx.get("https://api.pensionpro.com/v2/contacts").mock(
            return_value=httpx.Response(200, json=[
                {
                    "Id": 500, "FirstName": "Alice", "LastName": "Smith",
                    "SystemEmployee": True,
                    "Employee": {"Id": 50, "Active": True, "ContactId": 500},
                },
            ])
        )

        # Mock worktray members
        respx.get("https://api.pensionpro.com/v2/worktrayMembers").mock(
            return_value=httpx.Response(200, json=[
                {"Id": 1, "contactID": 500, "WorktrayID": 100, "RoleID": 1,
                 "Contact": {"FirstName": "Alice", "LastName": "Smith"}},
                {"Id": 2, "contactID": 500, "WorktrayID": 200, "RoleID": 2,
                 "Contact": {"FirstName": "Alice", "LastName": "Smith"}},
            ])
        )

        # Mock tasks — use side_effect to distinguish completed vs active
        respx.get("https://api.pensionpro.com/v2/tasks").mock(
            side_effect=lambda request: httpx.Response(200, json=[
                {
                    "Id": 10, "TaskName": "Review", "AssignedToId": 500, "TeamId": 100,
                    "TaskActive": "2026-04-01T00:00:00Z", "DateAdded": "2026-03-28T00:00:00Z",
                    "DateCompleted": None, "AcknowledgeDate": None,
                    "DaysToComp": 5, "Rejections": 0, "Rejected": False,
                    "TaskGroup": {"Name": "G1", "Project": {"Name": "Annual Val", "Id": 50}},
                },
            ]) if "null" in str(request.url) else httpx.Response(200, json=[
                {
                    "Id": 20, "TaskName": "Review", "AssignedToId": 500, "TeamId": 100,
                    "TaskActive": "2026-03-10T00:00:00Z", "DateAdded": "2026-03-08T00:00:00Z",
                    "DateCompleted": "2026-03-11T12:00:00Z", "AcknowledgeDate": "2026-03-10T01:00:00Z",
                    "DaysToComp": 5, "Rejections": 0, "Rejected": False,
                    "TaskGroup": {"Name": "G1", "Project": {"Name": "Annual Val", "Id": 50}},
                },
                {
                    "Id": 21, "TaskName": "Filing", "AssignedToId": 500, "TeamId": 200,
                    "TaskActive": "2026-03-15T00:00:00Z", "DateAdded": "2026-03-14T00:00:00Z",
                    "DateCompleted": "2026-03-16T00:00:00Z", "AcknowledgeDate": None,
                    "DaysToComp": 3, "Rejections": 1, "Rejected": True,
                    "TaskGroup": {"Name": "G2", "Project": {"Name": "5500 Filing", "Id": 51}},
                },
            ])
        )

        result = await get_employee_stats(client, name="Smith", days_back=30)

        assert result["employee"]["contact_id"] == 500
        assert result["employee"]["name"] == "Alice Smith"
        assert result["days_back"] == 30
        assert len(result["worktray_segments"]) == 2

        # Find worktray 100 segment (has 1 completed, 1 active)
        wt100 = next(s for s in result["worktray_segments"] if s["worktray_id"] == 100)
        assert wt100["workload"]["active_task_count"] == 1
        assert wt100["throughput"]["tasks_completed"] == 1
        # Compact: no task_type_breakdown or by_project
        assert "task_type_breakdown" not in wt100["throughput"]
        assert "by_project" not in wt100["throughput"]
        assert "tasks" not in wt100["workload"]

        # Find worktray 200 segment (has 1 completed with bounce-back, 0 active)
        wt200 = next(s for s in result["worktray_segments"] if s["worktray_id"] == 200)
        assert wt200["throughput"]["tasks_completed"] == 1
        assert wt200["quality"]["bounce_back_count"] == 1
        assert wt200["quality"]["total_rejections"] == 1

        # Aggregate
        assert result["aggregate"]["throughput"]["tasks_completed"] == 2
        assert result["aggregate"]["workload"]["active_task_count"] == 1
        assert result["aggregate"]["quality"]["bounce_back_count"] == 1

        # Cache and resource
        assert "resource_uri" in result
        assert result["resource_uri"] == "employee-stats://500"
        assert "cache_path" in result

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_worktray_memberships(self, client: PensionProClient, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

        respx.get("https://api.pensionpro.com/v2/contacts").mock(
            return_value=httpx.Response(200, json=[
                {
                    "Id": 500, "FirstName": "Alice", "LastName": "Smith",
                    "SystemEmployee": True,
                    "Employee": {"Id": 50, "Active": True, "ContactId": 500},
                },
            ])
        )
        respx.get("https://api.pensionpro.com/v2/worktrayMembers").mock(
            return_value=httpx.Response(200, json=[])
        )
        respx.get("https://api.pensionpro.com/v2/tasks").mock(
            return_value=httpx.Response(200, json=[])
        )

        result = await get_employee_stats(client, name="Smith", days_back=30)
        assert result["employee"]["contact_id"] == 500
        assert result["worktray_segments"] == []
        assert result["aggregate"]["throughput"]["tasks_completed"] == 0
        assert result["aggregate"]["workload"]["active_task_count"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_worktrays.py::TestGetEmployeeStats -v`
Expected: FAIL with `ImportError: cannot import name 'get_employee_stats'`

- [ ] **Step 3: Implement `get_employee_stats` and `read_cached_employee_stats`**

Add to `src/pension_pro_mcp/tools/worktrays.py` after `_compact_employee_segment`:

```python
async def get_employee_stats(
    client: PensionProClient,
    name: str,
    days_back: int = 30,
) -> dict[str, Any]:
    """Get per-employee performance analysis across all worktrays, segmented by worktray."""
    # Step 1: Resolve employee
    resolution = await _resolve_employee(client, name)
    if resolution["status"] != "found":
        return resolution

    contact_id = resolution["contact_id"]
    employee_name = resolution["name"]

    # Step 2: Fetch memberships and tasks in parallel
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    memberships, completed_tasks, active_tasks = await asyncio.gather(
        client.get_list(
            "/worktrayMembers",
            filters={"contactID": str(contact_id)},
            expand=["Contact"],
            top=1000,
            max_total=1000,
        ),
        client.get_list(
            "/tasks",
            filters={"AssignedToId": str(contact_id), "DateCompleted__ge": cutoff_iso},
            expand=["AssignedTo", "TaskGroup($expand=Project)"],
            top=1000,
            max_total=10000,
        ),
        client.get_list(
            "/tasks",
            filters={"AssignedToId": str(contact_id), "DateCompleted": "null"},
            expand=["AssignedTo", "TaskGroup($expand=Project)"],
            top=1000,
            max_total=10000,
        ),
    )

    # Step 3: Group tasks by TeamId (worktray)
    worktray_ids = {m["WorktrayID"] for m in memberships if m.get("WorktrayID")}

    completed_by_wt: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for task in completed_tasks:
        team_id = task.get("TeamId")
        if team_id is not None:
            completed_by_wt[team_id].append(task)

    active_by_wt: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for task in active_tasks:
        team_id = task.get("TeamId")
        if team_id is not None:
            active_by_wt[team_id].append(task)

    # Collect all worktray IDs the employee has activity in
    all_wt_ids = worktray_ids | set(completed_by_wt.keys()) | set(active_by_wt.keys())

    # Build worktray name lookup from memberships
    wt_names: dict[int, str | None] = {}
    for m in memberships:
        wt_id = m.get("WorktrayID")
        if wt_id:
            wt_names[wt_id] = None  # name not available from membership endpoint

    # Step 4: Compute per-worktray segments
    segments: list[dict[str, Any]] = []
    for wt_id in sorted(all_wt_ids):
        wt_completed = completed_by_wt.get(wt_id, [])
        wt_active = active_by_wt.get(wt_id, [])

        segment: dict[str, Any] = {
            "worktray_id": wt_id,
            "worktray_name": wt_names.get(wt_id),
            "workload": _compute_employee_workload(wt_active),
            "throughput": _compute_employee_throughput(wt_completed, days_back),
            "quality": _compute_employee_quality(wt_completed),
        }
        segments.append(segment)

    # Step 5: Compute aggregate
    aggregate = {
        "workload": _compute_employee_workload(active_tasks),
        "throughput": _compute_employee_throughput(completed_tasks, days_back),
        "quality": _compute_employee_quality(completed_tasks),
    }

    # Step 6: Build full result and cache
    full_result: dict[str, Any] = {
        "employee": {"contact_id": contact_id, "name": employee_name},
        "days_back": days_back,
        "worktray_segments": segments,
        "aggregate": aggregate,
    }

    cache_dir = _stats_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"employee-{contact_id}-{days_back}d.json"
    cache_file.write_text(json.dumps(full_result, indent=2))

    # Step 7: Return compact summary
    compact_segments = [_compact_employee_segment(s) for s in segments]
    compact_aggregate = {
        "workload": {k: v for k, v in aggregate["workload"].items() if k != "tasks"},
        "throughput": {
            k: v for k, v in aggregate["throughput"].items()
            if k not in ("task_type_breakdown", "by_project")
        },
        "quality": aggregate["quality"],
    }

    return {
        "employee": {"contact_id": contact_id, "name": employee_name},
        "days_back": days_back,
        "worktray_segments": compact_segments,
        "aggregate": compact_aggregate,
        "resource_uri": f"employee-stats://{contact_id}",
        "cache_path": str(cache_file),
    }


def read_cached_employee_stats(contact_id: int) -> dict[str, Any] | None:
    """Read cached stats for an employee, if available."""
    cache_dir = _stats_cache_dir()
    matches = sorted(
        cache_dir.glob(f"employee-{contact_id}-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        return None
    return json.loads(matches[0].read_text())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_worktrays.py::TestGetEmployeeStats -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pension_pro_mcp/tools/worktrays.py tests/test_worktrays.py
git commit -m "feat: add get_employee_stats tool with caching and compact response"
```

---

### Task 7: Register Tool and Resource in server.py

**Files:**
- Modify: `src/pension_pro_mcp/server.py`

- [ ] **Step 1: Update the import line**

In `src/pension_pro_mcp/server.py`, change the worktrays import (line 26) from:

```python
from pension_pro_mcp.tools.worktrays import get_worktrays, get_worktray, get_worktray_member_stats, read_cached_stats
```

to:

```python
from pension_pro_mcp.tools.worktrays import (
    get_worktrays, get_worktray, get_worktray_member_stats, read_cached_stats,
    get_employee_stats, read_cached_employee_stats,
)
```

- [ ] **Step 2: Add the tool registration**

After the `_worktray_stats_resource` function (after line 479), add:

```python
@mcp.tool(name="get_employee_stats")
@pipeline.wrap
async def _get_employee_stats(
    ctx: Context[ServerSession, AppContext],
    name: str,
    days_back: int = 30,
) -> dict:
    """Get individual employee performance analysis across all worktrays.

    Searches by last name, then computes per-worktray metrics for workload,
    throughput, and quality (rejections and bounce-backs). Returns a compact
    summary; full results cached and available via the employee-stats resource.

    If the name matches multiple employees, returns a candidate list to disambiguate.
    """
    client = ctx.request_context.lifespan_context.client
    return await get_employee_stats(client, name=name, days_back=days_back)


@mcp.resource("employee-stats://{contact_id}", name="employee_stats",
              description="Full employee stats from the most recent analysis. "
              "Run get_employee_stats first to populate the cache.",
              mime_type="application/json")
def _employee_stats_resource(contact_id: int) -> str:
    """Return cached full stats for an employee."""
    result = read_cached_employee_stats(contact_id)
    if result is None:
        return json.dumps({"error": f"No cached stats for employee {contact_id}. Run get_employee_stats first."})
    return json.dumps(result)
```

- [ ] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: All existing tests still PASS, no regressions

- [ ] **Step 4: Commit**

```bash
git add src/pension_pro_mcp/server.py
git commit -m "feat: register get_employee_stats tool and employee-stats resource"
```

---

### Task 8: Run Full Suite and Verify

- [ ] **Step 1: Run the complete test suite**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Verify import works end-to-end**

Run: `python -c "from pension_pro_mcp.tools.worktrays import get_employee_stats; print('OK')"`
Expected: Prints `OK`

- [ ] **Step 3: Final commit if any cleanup needed**

If any fixes were needed, commit them:

```bash
git add -A
git commit -m "chore: final cleanup for employee stats feature"
```
