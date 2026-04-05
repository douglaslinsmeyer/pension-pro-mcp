# Task Group Cycle Times by Project Template

**Issue:** #5 — Worktray analytics: task group cycle time by project template
**Date:** 2026-04-04

## Goal

Add a tool to compute task group cycle times segmented by project template, revealing which workflows are slow and which steps are bottlenecks.

## Tool Signature

```python
async def get_task_group_cycle_times(
    client: PensionProClient,
    days_back: int = 90,
    plan_id: int | None = None,
    template_id: int | None = None,
    include_steps: bool = False,
) -> dict:
```

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `days_back` | `int` | `90` | Lookback window from now |
| `plan_id` | `int \| None` | `None` | Filter to task groups on projects for this plan |
| `template_id` | `int \| None` | `None` | Filter to a specific project template |
| `include_steps` | `bool` | `False` | Fetch per-task step durations and identify bottlenecks |

## Data Fetching

### Primary query: completed task groups

```
GET /v2/taskgroups
  $filter=DateCompleted ge '{cutoff_iso}'
          [and Project/PlanId eq {plan_id}]
          [and Project/ProjectTemplateId eq {template_id}]
  $expand=Project($expand=ProjectTemplate)
  $top=1000
  max_total=10000
```

This returns task groups with their parent project and template metadata in a single paginated query.

**Note on nested OData filters:** `build_odata_params` doesn't currently support nested property paths like `Project/PlanId`. Two options:
1. Add nested path support to `build_odata_params` (e.g., `Project/PlanId` key passes through as-is)
2. Fetch all completed task groups and filter by `plan_id`/`template_id` in Python after expanding the Project

Option 1 is preferred if the API supports nested filters (OData v4 does). If not, fall back to option 2 with post-filtering. The implementation should try option 1 first.

### Step detail query (when `include_steps=True`)

For each completed task group:

```
GET /v2/taskgroups/{task_group_id}/tasks
```

Concurrency-limited with `asyncio.Semaphore(10)` to avoid hammering the API. If the number of groups exceeds 500, log a warning about potential slowness.

## Metrics

### Per-template aggregation

Task groups are grouped by `Project.ProjectTemplateId`. For each template:

| Metric | Calculation |
|--------|-------------|
| `groups_completed` | Count of completed task groups |
| `avg_cycle_days` | Mean of `DateCompleted - DateActivated` in days |
| `median_cycle_days` | Median of cycle times |
| `min_cycle_days` | Minimum cycle time |
| `max_cycle_days` | Maximum cycle time |
| `sla_adherence_pct` | Percentage where `DateCompleted <= DateDue` |
| `groups_without_due_date` | Count excluded from SLA calc (no `DateDue`) |

Task groups missing `DateActivated` are skipped entirely (no cycle time computable).

Groups without `DateDue` are excluded from SLA percentage and counted separately.

Results sorted by `groups_completed` descending.

### Per-step breakdown (when `include_steps=True`)

Tasks within each group are sorted by `Order`. For each step position:

| Metric | Calculation |
|--------|-------------|
| `order` | Task order within the group |
| `task_name` | Name of the task at this step |
| `avg_duration_days` | Mean of `DateCompleted - DateActivated` for this step |
| `median_duration_days` | Median duration |
| `is_bottleneck` | `True` for the step with the longest avg duration |

Steps with missing `DateActivated` or `DateCompleted` are skipped. Step durations are aggregated across all groups of the same template, matched by `Order`.

## Response Shape

```json
{
  "by_template": [
    {
      "template_id": 42,
      "template_name": "DC Distribution Rqst",
      "groups_completed": 145,
      "avg_cycle_days": 8.2,
      "median_cycle_days": 6.5,
      "min_cycle_days": 1.0,
      "max_cycle_days": 32.0,
      "sla_adherence_pct": 72.0,
      "groups_without_due_date": 12,
      "steps": [
        {
          "order": 1,
          "task_name": "Review Request",
          "avg_duration_days": 1.2,
          "median_duration_days": 0.8,
          "is_bottleneck": false
        },
        {
          "order": 2,
          "task_name": "Distribution Confirmation",
          "avg_duration_days": 3.1,
          "median_duration_days": 2.5,
          "is_bottleneck": true
        }
      ]
    }
  ],
  "summary": {
    "total_groups_completed": 412,
    "templates_analyzed": 8,
    "period_days": 90,
    "cutoff_date": "2026-01-04T00:00:00Z"
  }
}
```

The `steps` key is only present when `include_steps=True`.

## Module Placement

### New module: `src/pension_pro_mcp/tools/analytics.py`

This tool is global (not worktray-scoped), so a dedicated analytics module keeps concerns separated. Future analytics tools (e.g., issue #2 throughput/aging/bottleneck) can also live here.

### Private helper functions

| Function | Purpose |
|----------|---------|
| `_compute_cycle_times(task_groups)` | Groups by template, computes per-template stats |
| `_compute_step_durations(tasks)` | Per-step timing for one task group's tasks |
| `_aggregate_step_durations(all_steps)` | Merges step durations across groups of the same template, identifies bottleneck |

### Registration in `server.py`

- Import `get_task_group_cycle_times` from `tools.analytics`
- Register with `@mcp.tool(name="get_task_group_cycle_times")` + `@pipeline.wrap`
- Standard pattern: extract client from context, pass through parameters

## Response Tier

Single-tier response (no disk caching). The output is already aggregated and compact. If response size becomes a problem, we can revise to a two-tier pattern with disk cache + MCP resource (matching `get_worktray_member_stats`).

## Testing

### Test file: `tests/test_analytics.py`

| Test class | Coverage |
|------------|----------|
| `TestComputeCycleTimes` | Unit tests for `_compute_cycle_times`: multiple templates, varied dates, missing `DateActivated`, missing `DateDue`, single template |
| `TestComputeStepDurations` | Unit tests for `_compute_step_durations`: step timing, missing dates skipped |
| `TestAggregateStepDurations` | Merging across groups, bottleneck identification |
| `TestGetTaskGroupCycleTimes` | Integration test with respx mocks for `/taskgroups` and `/taskgroups/{id}/tasks`, with and without `include_steps`, with optional filters |

### Edge cases

- Empty results (no completed task groups in window)
- All groups missing `DateActivated` (all skipped)
- All groups missing `DateDue` (SLA shows `null`, `groups_without_due_date` equals total)
- Single template with one group
- `include_steps` with tasks missing dates

### Test pattern

```python
@respx.mock
@pytest.mark.asyncio
async def test_name(client: PensionProClient) -> None:
    respx.get("https://api.pensionpro.com/v2/taskgroups").mock(
        return_value=httpx.Response(200, json=[...])
    )
    result = await get_task_group_cycle_times(client, days_back=90)
    assert result["summary"]["templates_analyzed"] == 2
```
