# Performance Stats by Project Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a project-type dimension to worktray member performance stats, enabling apples-to-apples comparisons of members working the same workflows.

**Architecture:** Modify `_compute_performance_stats` to sub-group tasks by project name (from expanded `TaskGroup.Project.Name`). Per-member `by_project` breakdowns go in the full cache; aggregate `by_project` with `top_performers` goes in the compact tool response. No new API calls — uses existing expanded data.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, respx

**Spec:** `docs/superpowers/specs/2026-04-04-performance-by-project-design.md`

---

### Task 1: Add project names to test data and verify `by_project` on per-member performance

**Files:**
- Modify: `src/pension_pro_mcp/tools/worktrays.py:106-191`
- Test: `tests/test_worktrays.py`

- [ ] **Step 1: Update test data to include TaskGroup.Project.Name and write failing test**

In `tests/test_worktrays.py`, replace the `TestComputePerformanceStats.test_computes_per_member_metrics` method with a version that includes project names in the task data and asserts on `by_project`:

```python
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
                "TaskGroup": {"Name": "G1", "Project": {"Name": "DC Distribution Rqst", "Id": 50}},
            },
            {
                "Id": 101, "TaskName": "Review", "AssignedToId": 1,
                "TaskActive": "2026-03-05T00:00:00Z",
                "DateCompleted": "2026-03-05T12:00:00Z",
                "AcknowledgeDate": "2026-03-05T01:00:00Z",
                "Rejections": 1,
                "TaskGroup": {"Name": "G2", "Project": {"Name": "Loan Request", "Id": 51}},
            },
            {
                "Id": 102, "TaskName": "Filing", "AssignedToId": 2,
                "TaskActive": "2026-03-10T00:00:00Z",
                "DateCompleted": "2026-03-12T00:00:00Z",
                "AcknowledgeDate": None,
                "Rejections": 0,
                "TaskGroup": {"Name": "G1", "Project": {"Name": "DC Distribution Rqst", "Id": 50}},
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

        # by_project breakdown
        assert len(alice["performance"]["by_project"]) == 2
        dc = next(p for p in alice["performance"]["by_project"] if p["project"] == "DC Distribution Rqst")
        assert dc["tasks_completed"] == 1
        assert dc["avg_completion_hours"] == 24.0
        loan = next(p for p in alice["performance"]["by_project"] if p["project"] == "Loan Request")
        assert loan["tasks_completed"] == 1
        assert loan["avg_completion_hours"] == 12.0
        assert loan["rejection_rate"] == 1.0  # 1 rejection / 1 task

        bob = next(m for m in result["members"] if m["contact_id"] == 2)
        assert bob["performance"]["tasks_completed"] == 1
        assert bob["performance"]["avg_pickup_hours"] is None  # no acknowledge dates
        assert len(bob["performance"]["by_project"]) == 1
        assert bob["performance"]["by_project"][0]["project"] == "DC Distribution Rqst"

        assert result["aggregate"]["total_completed"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_worktrays.py::TestComputePerformanceStats::test_computes_per_member_metrics -v`
Expected: FAIL — `by_project` key not in performance dict.

- [ ] **Step 3: Implement per-member `by_project` in `_compute_performance_stats`**

In `src/pension_pro_mcp/tools/worktrays.py`, replace `_compute_performance_stats` (lines 106-191) with:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_worktrays.py::TestComputePerformanceStats::test_computes_per_member_metrics -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pension_pro_mcp/tools/worktrays.py tests/test_worktrays.py
git commit -m "feat: add by_project breakdown to _compute_performance_stats"
```

---

### Task 2: Update remaining performance tests and add aggregate by_project test

**Files:**
- Modify: `tests/test_worktrays.py`

- [ ] **Step 1: Update zero-completions test to assert on by_project**

In `tests/test_worktrays.py`, update `TestComputePerformanceStats.test_member_with_zero_completions`:

```python
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
        assert alice["performance"]["by_project"] == []
        assert result["aggregate"]["total_completed"] == 0
        assert result["aggregate"]["team_avg_completion_hours"] is None
        assert result["aggregate"]["by_project"] == []
```

- [ ] **Step 2: Update missing-task-active test to include project data and verify by_project**

In `tests/test_worktrays.py`, update `TestComputePerformanceStats.test_tasks_with_missing_task_active`:

```python
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
                "TaskGroup": {"Name": "G1", "Project": {"Name": "DC Distribution Rqst", "Id": 50}},
            },
        ]
        result = _compute_performance_stats(completed_tasks, members)
        alice = result["members"][0]
        assert alice["performance"]["tasks_completed"] == 1
        assert alice["performance"]["avg_completion_hours"] is None
        assert len(alice["performance"]["by_project"]) == 1
        assert alice["performance"]["by_project"][0]["project"] == "DC Distribution Rqst"
        assert alice["performance"]["by_project"][0]["avg_completion_hours"] is None
```

- [ ] **Step 3: Add test for aggregate by_project with multiple members on same project**

Add to `TestComputePerformanceStats`:

```python
    def test_aggregate_by_project(self) -> None:
        members = [
            {"contactID": 1, "RoleID": 10, "Contact": {"FirstName": "Alice", "LastName": "Smith"}},
            {"contactID": 2, "RoleID": 20, "Contact": {"FirstName": "Bob", "LastName": "Jones"}},
        ]
        completed_tasks = [
            {
                "Id": 100, "TaskName": "Review", "AssignedToId": 1,
                "TaskActive": "2026-03-01T00:00:00Z",
                "DateCompleted": "2026-03-02T00:00:00Z",
                "AcknowledgeDate": None, "Rejections": 0,
                "TaskGroup": {"Name": "G1", "Project": {"Name": "DC Distribution Rqst", "Id": 50}},
            },
            {
                "Id": 101, "TaskName": "Review", "AssignedToId": 2,
                "TaskActive": "2026-03-05T00:00:00Z",
                "DateCompleted": "2026-03-06T00:00:00Z",
                "AcknowledgeDate": None, "Rejections": 0,
                "TaskGroup": {"Name": "G2", "Project": {"Name": "DC Distribution Rqst", "Id": 51}},
            },
            {
                "Id": 102, "TaskName": "Filing", "AssignedToId": 1,
                "TaskActive": "2026-03-10T00:00:00Z",
                "DateCompleted": "2026-03-10T06:00:00Z",
                "AcknowledgeDate": None, "Rejections": 0,
                "TaskGroup": {"Name": "G3", "Project": {"Name": "Loan Request", "Id": 52}},
            },
        ]
        result = _compute_performance_stats(completed_tasks, members)
        agg = result["aggregate"]
        assert len(agg["by_project"]) == 2
        dc = next(p for p in agg["by_project"] if p["project"] == "DC Distribution Rqst")
        assert dc["tasks_completed"] == 2
        assert dc["member_count"] == 2  # Alice and Bob both worked on DC
        # Alice: 24h, Bob: 24h -> avg 24h
        assert dc["avg_completion_hours"] == 24.0
        loan = next(p for p in agg["by_project"] if p["project"] == "Loan Request")
        assert loan["tasks_completed"] == 1
        assert loan["member_count"] == 1
        assert loan["avg_completion_hours"] == 6.0
```

- [ ] **Step 4: Run all performance tests**

Run: `uv run pytest tests/test_worktrays.py::TestComputePerformanceStats -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_worktrays.py
git commit -m "test: update performance tests for by_project and add aggregate test"
```

---

### Task 3: Update compact summary and integration tests

**Files:**
- Modify: `src/pension_pro_mcp/tools/worktrays.py:281-293` (`_compact_member`)
- Modify: `src/pension_pro_mcp/tools/worktrays.py:368-388` (`get_worktray_member_stats` compact response)
- Test: `tests/test_worktrays.py`

- [ ] **Step 1: Update integration test to verify compact response includes aggregate by_project with top_performers**

In `tests/test_worktrays.py`, update `TestGetWorktrayMemberStats.test_assembles_full_response`. Add a second completed task for a different member on the same project so `top_performers` has data. Replace the method:

```python
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
        assert result["member_count"] == 2
        assert len(result["top_members"]) == 2
        alice = next(m for m in result["top_members"] if m["contact_id"] == 500)
        assert alice["name"] == "Alice Smith"
        assert alice["workload"]["active_task_count"] == 1
        assert alice["performance"]["tasks_completed"] == 1
        assert "task_type_breakdown" not in alice["performance"]  # stripped in compact
        assert "by_project" not in alice["performance"]  # stripped in compact
        assert "tasks" not in alice["workload"]  # stripped in compact
        assert result["aggregate"]["workload"]["total_active"] == 1
        assert result["aggregate"]["performance"]["total_completed"] == 1
        assert "throughput_per_day" in result["aggregate"]["queue_health"]
        assert "overdue_tasks" not in result["aggregate"]["queue_health"]  # stripped in compact
        assert "overdue_by_type" in result["aggregate"]["queue_health"]
        # Verify aggregate by_project with top_performers
        agg_projects = result["aggregate"]["performance"]["by_project"]
        assert len(agg_projects) == 1
        assert agg_projects[0]["project"] == "Annual Val"
        assert agg_projects[0]["tasks_completed"] == 1
        assert "top_performers" in agg_projects[0]
        assert agg_projects[0]["top_performers"][0]["name"] == "Alice Smith"
        assert "full_results" in result
        assert "resource_uri" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_worktrays.py::TestGetWorktrayMemberStats::test_assembles_full_response -v`
Expected: FAIL — `by_project` not stripped from compact member, `top_performers` not in aggregate.

- [ ] **Step 3: Update `_compact_member` to strip `by_project`**

In `src/pension_pro_mcp/tools/worktrays.py`, replace `_compact_member` (lines 281-293):

```python
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
```

- [ ] **Step 4: Update `get_worktray_member_stats` to add `top_performers` to aggregate `by_project`**

In `src/pension_pro_mcp/tools/worktrays.py`, in the `get_worktray_member_stats` function, after the line `perf_by_id = {m["contact_id"]: m["performance"] for m in performance["members"]}` and after the merge loop, add top_performers enrichment. Replace the section from the merge loop through the compact response building (the block starting at `# Merge per-member results` through the `return` statement):

```python
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
```

- [ ] **Step 5: Run integration tests**

Run: `uv run pytest tests/test_worktrays.py::TestGetWorktrayMemberStats -v`
Expected: All 2 tests PASS.

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/test_worktrays.py -v`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/pension_pro_mcp/tools/worktrays.py tests/test_worktrays.py
git commit -m "feat: add by_project to compact summary with top_performers enrichment"
```

---

### Task 4: Final verification

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass (1 pre-existing failure in test_projects.py is OK).

- [ ] **Step 2: Verify module imports**

Run: `uv run python -c "from pension_pro_mcp.tools.worktrays import get_worktray_member_stats; print('OK')"`
Expected: `OK`
