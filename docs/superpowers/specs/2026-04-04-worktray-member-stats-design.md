# Design: get_worktray_member_stats

**Date:** 2026-04-04
**Issue:** douglaslinsmeyer/pension-pro-mcp#3

## Purpose

Add a `get_worktray_member_stats` MCP tool that provides per-member performance metrics for a worktray, covering workload balancing, performance review, and queue health monitoring in a single response.

## Tool Signature

```python
async def get_worktray_member_stats(
    client: PensionProClient,
    worktray_id: int,
    days_back: int = 30,
) -> dict[str, Any]
```

- `worktray_id` -- which worktray to analyze
- `days_back` -- lookback window for completed task metrics (default 30 days)

## Architecture: Approach B (Composable Helpers)

One MCP tool entry point backed by three internal pure-function helpers for metric computation. The helpers are independently testable and reusable for future analytics tools (issue #2).

### Data Fetching

Three independent API queries, fetched concurrently via `asyncio.gather`:

1. **Completed tasks** -- tasks finished within the lookback window
   ```
   GET /v2/tasks?$filter=TeamId eq {worktray_id} and DateCompleted ge {cutoff_iso}
       &$expand=AssignedTo,TaskGroup($expand=Project)
   ```

2. **Active tasks** -- currently open tasks in the worktray
   ```
   GET /v2/tasks?$filter=TeamId eq {worktray_id} and DateCompleted eq null
       &$expand=AssignedTo,TaskGroup($expand=Project)
   ```

3. **Worktray members** -- team membership with contact details
   ```
   GET /v2/worktrayMembers?$expand=Contact
   ```
   Filtered client-side by `WorktrayID == worktray_id` (matches existing `get_worktray` pattern).

The `$expand` parameters provide:
- `AssignedTo` -- employee name on tasks without extra contact lookups
- `TaskGroup($expand=Project)` -- project name and ID for context on each task
- `Contact` on worktray members -- member names, ensures we have names even for members with zero task completions

### Cutoff Date Computation

```python
from datetime import datetime, timedelta, timezone
cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
```

Used in the OData `$filter` for the completed tasks query.

## Metric Computation Helpers

All three helpers are pure functions (no I/O). They accept lists of task dicts and member dicts, return plain dicts.

### `_compute_workload_stats(active_tasks, members) -> dict`

Per member (keyed by `contact_id`):
- `active_task_count` -- number of active tasks assigned to them
- `tasks` -- list of active task details:
  - `task_name`, `project` (from TaskGroup.Project.Name), `age_days` (days since TaskActive or DateAdded)

Aggregate:
- `total_active` -- total open tasks in the worktray
- `unassigned_count` -- active tasks with no `AssignedToId`

### `_compute_performance_stats(completed_tasks, members) -> dict`

Per member (keyed by `contact_id`):
- `tasks_completed` -- count within the window
- `avg_completion_hours` -- mean of `DateCompleted - TaskActive` in hours (only where both are non-null)
- `avg_pickup_hours` -- mean of `AcknowledgeDate - TaskActive` in hours (only where both are non-null)
- `rejection_rate` -- `sum(Rejections) / tasks_completed` (0.0 if no completions)
- `task_type_breakdown` -- list of `{task_name, count}` sorted by count descending

Aggregate:
- `total_completed` -- total tasks completed in window
- `team_avg_completion_hours` -- overall mean completion time for comparison

### `_compute_queue_health(active_tasks, completed_tasks, days_back) -> dict`

- `throughput_per_day` -- `total_completed / days_back` (float, rounded to 2 decimals)
- `intake_per_day` -- tasks from both the active and completed sets whose `DateAdded` falls within the window, divided by `days_back` (float, rounded to 2 decimals). Uses the union of both query results deduplicated by task `Id`.
- `queue_growing` -- boolean, `intake_per_day > throughput_per_day`
- `oldest_active_task_age_days` -- age in days of the oldest open task (by TaskActive or DateAdded)
- `overdue_count` -- active tasks where `age_days > DaysToComp` (when DaysToComp is non-null)
- `overdue_tasks` -- list of overdue task details:
  - `task_id`, `task_name`, `project`, `age_days`, `days_to_comp`

## Response Shape

```json
{
    "worktray_id": 5304,
    "period_days": 30,
    "members": [
        {
            "contact_id": 911697,
            "name": "Jane Smith",
            "role_id": 428315,
            "workload": {
                "active_task_count": 5,
                "tasks": [
                    {"task_name": "Initial Review", "project": "2024 Annual Valuation", "age_days": 3}
                ]
            },
            "performance": {
                "tasks_completed": 12,
                "avg_completion_hours": 18.5,
                "avg_pickup_hours": 2.3,
                "rejection_rate": 0.08,
                "task_type_breakdown": [
                    {"task_name": "Initial Review", "count": 8}
                ]
            }
        }
    ],
    "aggregate": {
        "workload": {
            "total_active": 15,
            "unassigned_count": 3
        },
        "performance": {
            "total_completed": 42,
            "team_avg_completion_hours": 22.1
        },
        "queue_health": {
            "throughput_per_day": 1.4,
            "intake_per_day": 1.6,
            "queue_growing": true,
            "oldest_active_task_age_days": 45,
            "overdue_count": 2,
            "overdue_tasks": [
                {"task_id": 42, "task_name": "Final Review", "project": "2024 5500 Filing", "age_days": 12, "days_to_comp": 7}
            ]
        }
    }
}
```

Members with zero completions and zero active tasks still appear (sourced from worktray members list, not from task data).

## Date Parsing

Task date fields (`DateCompleted`, `TaskActive`, `AcknowledgeDate`, `DateAdded`) come as ISO 8601 strings from the API. Parse with `datetime.fromisoformat`. Handle null values by skipping that task for the relevant metric rather than erroring.

## Pagination

Busy worktrays may have thousands of completed tasks in a 30-day window. Use `client.get_list()` with a reasonable `max_total` (e.g., 10000) to cap query size. The `days_back` filter keeps the result set bounded by default.

## File Organization

- **`src/pension_pro_mcp/tools/worktrays.py`** -- add `get_worktray_member_stats` and the three `_compute_*` helpers to the existing module
- **`src/pension_pro_mcp/server.py`** -- register the new tool under the worktray section
- **`tests/test_worktrays.py`** -- add test classes for the new function

## Testing Strategy

### Unit tests for helpers (pure functions, no mocking)

- `TestComputeWorkloadStats` -- crafted task/member dicts, verify per-member counts and unassigned count
- `TestComputePerformanceStats` -- verify avg completion/pickup hours, rejection rate, task type breakdown; edge case: member with zero completions
- `TestComputeQueueHealth` -- verify throughput/intake rates, overdue detection; edge case: no completed tasks, no active tasks

### Integration test for the tool function (respx mocking)

- `TestGetWorktrayMemberStats` -- mock the three API calls, verify the assembled response structure
- Edge cases: empty worktray (no tasks, no members), tasks missing `TaskActive`/`AcknowledgeDate`/`DaysToComp`

## OData Considerations

- Nested expand syntax `TaskGroup($expand=Project)` is passed through the existing `build_odata_params` and query string construction in `get_list` without percent-encoding, which should work with the PensionPro API.
- The `ge` (greater than or equal) operator on `DateCompleted` uses ISO 8601 format without quotes, matching the existing OData convention in `build_odata_params` for date-like strings.

## Handling of `ge` Date Filter

The existing `build_odata_params` treats values as `eq` comparisons. Extend it to support `__ge` and `__le` operator suffixes alongside the existing `__contains` pattern. This keeps filter construction centralized and benefits future analytics tools that also need date-range queries.

Example: `{"DateCompleted__ge": "2026-03-05T00:00:00Z"}` produces `DateCompleted ge 2026-03-05T00:00:00Z` (unquoted, matching OData date literal conventions).
