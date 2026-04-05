# Design: Performance Stats by Project Type

**Date:** 2026-04-04
**Issue:** douglaslinsmeyer/pension-pro-mcp#4

## Purpose

Add a project-type dimension to `get_worktray_member_stats` performance metrics, enabling apples-to-apples member comparisons within the same workflow type.

## Approach: C (Both per-member and aggregate)

Full cached result gets per-member `by_project` breakdowns. Compact tool response gets an aggregate `by_project` section with top performers per project. Fits the existing compact-vs-full pattern.

## Changes to `_compute_performance_stats`

### Per-member output gains `by_project`

Group each member's completed tasks by `_task_project_name(task)` (the expanded `TaskGroup.Project.Name`). For each project group, compute the same metrics as the member totals:

```python
"by_project": [
    {
        "project": "DC Distribution Rqst",
        "tasks_completed": 150,
        "avg_completion_hours": 6.2,
        "avg_pickup_hours": 5.8,
        "rejection_rate": 0.01,
    },
]
```

Sorted by `tasks_completed` descending. Existing top-level per-member metrics remain as totals across all projects.

Tasks with no project name (null `TaskGroup` or `Project`) are grouped under `"Unknown"`.

### Aggregate output gains `by_project`

Computed across all members' tasks grouped by project name:

```python
"by_project": [
    {
        "project": "DC Distribution Rqst",
        "tasks_completed": 2841,
        "avg_completion_hours": 12.3,
        "member_count": 45,
    },
]
```

Sorted by `tasks_completed` descending. `member_count` is the number of distinct assignees who completed at least one task for that project type.

## Changes to compact summary

### `_compact_member` — strips `by_project`

Per-member `by_project` is full-cache-only data. The compact member representation already strips `task_type_breakdown`; it also strips `by_project`.

### Compact aggregate gains `by_project` with `top_performers`

The aggregate `by_project` list is included in the compact response (one entry per project type — bounded by distinct project names, typically 10-30). Each entry gains a `top_performers` list (top 3 members by volume for that project) with name, tasks_completed, and avg_completion_hours:

```json
{
    "project": "DC Distribution Rqst",
    "tasks_completed": 2841,
    "avg_completion_hours": 12.3,
    "member_count": 45,
    "top_performers": [
        {"name": "Mandie Roggenkamp", "tasks_completed": 150, "avg_completion_hours": 6.2},
        {"name": "Selvakumar Rajendran", "tasks_completed": 130, "avg_completion_hours": 10.5},
        {"name": "Madhumita Janani", "tasks_completed": 120, "avg_completion_hours": 14.1}
    ]
}
```

The `top_performers` enrichment happens in `get_worktray_member_stats` during the merge step (not inside `_compute_performance_stats`), since it needs both the aggregate project data and the per-member project data.

## Data flow

No new API calls. Completed tasks already have `TaskGroup.Project.Name` expanded.

1. `_compute_performance_stats` groups tasks by `(assignee, project_name)`, computes per-member `by_project` and aggregate `by_project`
2. `get_worktray_member_stats` enriches the aggregate `by_project` with `top_performers` from per-member data, writes full result to cache, builds compact response
3. `_compact_member` strips `by_project` from individual members in the compact response

## Implementation detail

Inside `_compute_performance_stats`, the per-member loop already iterates tasks and computes hours/rejections. Add a secondary grouping:

```python
# Per member, group tasks by project
project_groups: dict[str, list[dict]] = defaultdict(list)
for task in tasks:
    project_groups[_task_project_name(task) or "Unknown"].append(task)
```

Then compute the same metric set (avg_completion_hours, avg_pickup_hours, rejection_rate) for each project group. This reuses the same computation logic as the member totals.

For the aggregate `by_project`, accumulate across all members during the same loop.

## Project name handling

Project names are used as-is from the API (e.g., "RMD Distribution - 2025", "RMD Distribution - 2026" remain separate). Year suffixes are not normalized — the AI consumer can group by prefix if needed. This preserves the ability to compare year-over-year performance.

## Testing

### Update `TestComputePerformanceStats`

- **`test_computes_per_member_metrics`** — add tasks with different project names (via `TaskGroup.Project.Name`), verify `by_project` appears on each member with correct per-project metrics
- **`test_member_with_zero_completions`** — verify `by_project` is empty list
- **`test_tasks_with_missing_task_active`** — verify per-project avg_completion_hours is None when TaskActive is missing

### New test

- **`test_aggregate_by_project`** — verify aggregate `by_project` has correct totals and member counts across multiple members working the same project type

### Update `TestGetWorktrayMemberStats`

- **`test_assembles_full_response`** — verify aggregate `by_project` with `top_performers` appears in compact response, verify `by_project` stripped from compact members

## File organization

All changes in existing files:
- `src/pension_pro_mcp/tools/worktrays.py` — modify `_compute_performance_stats`, `_compact_member`, `get_worktray_member_stats`
- `tests/test_worktrays.py` — update existing tests, add new test
