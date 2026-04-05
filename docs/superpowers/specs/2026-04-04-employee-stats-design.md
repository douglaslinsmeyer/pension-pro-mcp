# Employee Stats Tool Design

## Summary

Add `get_employee_stats(name, days_back=30)` — individual employee performance analysis across all worktrays they belong to, segmented by worktray. Enables managers to assess a person's throughput, workload, and quality metrics.

Addresses [GitHub issue #3](https://github.com/douglaslinsmeyer/pension-pro-mcp/issues/3) (the per-member stats portion that the existing `get_worktray_member_stats` doesn't cover — individual-focused analysis).

## Tool Interface

```python
async def get_employee_stats(
    client: PensionProClient,
    name: str,
    days_back: int = 30,
) -> dict[str, Any]:
```

- `name` — free-text search matched against employee last names via `LastName__contains`
- `days_back` — lookback window for completed task metrics (default 30)

### Name Resolution

1. Search `/contacts` filtered by `LastName__contains=name` and `SystemEmployee=true`, expand `Employee`
2. Filter to contacts whose expanded Employee is active (`Employee.Active`)
3. **0 matches** — return error with suggestion to try a different name
4. **1 match** — proceed with stats
5. **2+ matches** — return candidate list (name + contact ID) so the caller can re-invoke with a more specific name

## Data Fetching

Once the employee's `ContactId` is resolved, three parallel API calls via `asyncio.gather()`:

1. **Worktray memberships** — `GET /worktrayMembers` filtered by `contactID={contactId}`, expand `Contact`
2. **Completed tasks** — `GET /tasks` filtered by `AssignedToId={contactId}` and `DateCompleted__ge={cutoff}`, expand `AssignedTo,TaskGroup($expand=Project)`
3. **Active tasks** — `GET /tasks` filtered by `AssignedToId={contactId}` and `DateCompleted=null`, expand same

Tasks are grouped by `TeamId` to produce per-worktray segments.

## Metrics

All metrics computed per worktray segment and as a cross-worktray aggregate.

### Workload (from active tasks)

| Metric | Description |
|--------|-------------|
| `active_task_count` | Current open tasks in this worktray |
| `oldest_task_age_days` | Age of oldest open task |

### Throughput (from completed tasks)

| Metric | Description |
|--------|-------------|
| `tasks_completed` | Count within the time window |
| `avg_completion_hours` | Mean `TaskActive` to `DateCompleted` duration |
| `avg_pickup_hours` | Mean `TaskActive` to `AcknowledgeDate` duration |
| `tasks_per_day` | `tasks_completed / days_back` |

### Quality

| Metric | Description |
|--------|-------------|
| `rejection_rate` | Percentage of completed tasks where `Rejections > 0` (employee rejected the task) |
| `total_rejections` | Sum of `Rejections` across completed tasks |
| `bounce_back_count` | Completed tasks where `Rejected == true` (sent back from a downstream review step) |
| `bounce_back_rate` | `bounce_back_count / tasks_completed` |

### Breakdowns (full version only)

| Metric | Description |
|--------|-------------|
| `task_type_breakdown` | Counter by `TaskName` |
| `by_project` | Per-project task count and avg completion hours |

## Response Shape

### Compact (returned to caller)

```json
{
    "employee": {"contact_id": 123, "name": "Jane Smith"},
    "days_back": 30,
    "worktray_segments": [
        {
            "worktray_id": 10,
            "worktray_name": "Compliance",
            "workload": {"active_task_count": 5, "oldest_task_age_days": 12},
            "throughput": {"tasks_completed": 42, "avg_completion_hours": 18.3, "avg_pickup_hours": 2.1, "tasks_per_day": 1.4},
            "quality": {"rejection_rate": 0.05, "total_rejections": 2, "bounce_back_count": 3, "bounce_back_rate": 0.07}
        }
    ],
    "aggregate": {
        "workload": {"active_task_count": 12, "oldest_task_age_days": 15},
        "throughput": {"tasks_completed": 87, "avg_completion_hours": 20.1, "avg_pickup_hours": 2.5, "tasks_per_day": 2.9},
        "quality": {"rejection_rate": 0.04, "total_rejections": 3, "bounce_back_count": 5, "bounce_back_rate": 0.06}
    },
    "resource_uri": "employee-stats://123",
    "cache_path": "~/.cache/pension-pro-mcp/stats/employee-123-30d.json"
}
```

Compaction strips `task_type_breakdown`, `by_project`, and individual task lists.

### Full (cached to disk)

Same structure with breakdowns and task-level detail included in each segment.

## Caching

- **Path:** `~/.cache/pension-pro-mcp/stats/employee-{contactId}-{days_back}d.json`
- **Resource URI:** `employee-stats://{contact_id}` reads most recent cached file
- Follows existing `_stats_cache_dir()` pattern for cross-platform support

## Code Organization

All new code in existing files:

### `tools/worktrays.py`

- `get_employee_stats(client, name, days_back=30)` — main tool function
- `_resolve_employee(client, name)` — name search + employee filter helper
- `_compute_employee_workload(active_tasks)` — per-segment workload
- `_compute_employee_throughput(completed_tasks, days_back)` — per-segment throughput
- `_compute_employee_quality(completed_tasks)` — per-segment quality
- `_compact_employee_segment(segment)` — strip detail for compact response

Reuses existing helpers: `_parse_dt`, `_task_age_days`, `_task_project_name`, `_stats_cache_dir`.

### `server.py`

- `@mcp.tool(name="get_employee_stats")` with `@pipeline.wrap`
- `@mcp.resource("employee-stats://{contact_id}")` for cached data access

### `tests/test_worktrays.py`

New test classes following existing patterns:
- `TestResolveEmployee` — name search, filtering, disambiguation
- `TestComputeEmployeeWorkload` — active task metrics
- `TestComputeEmployeeThroughput` — completion/pickup time calculations
- `TestComputeEmployeeQuality` — rejection and bounce-back metrics
- `TestGetEmployeeStats` — integration test with respx mocks for full flow
