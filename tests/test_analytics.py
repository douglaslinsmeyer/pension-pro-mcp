"""Tests for analytics tools."""

import httpx
import pytest
import respx

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.analytics import (
    _aggregate_step_durations,
    _compute_cycle_times,
    _compute_step_durations,
    get_task_group_cycle_times,
)


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

    def test_falls_back_to_date_added_when_date_activated_is_none(self) -> None:
        task_groups = [
            {
                "Id": 1,
                "DateActivated": None,
                "DateAdded": "2026-01-01T00:00:00Z",
                "DateCompleted": "2026-01-09T00:00:00Z",
                "DateDue": "2026-01-15T00:00:00Z",
                "Project": {
                    "ProjectTemplateId": 10,
                    "ProjectTemplate": {"Name": "Template A"},
                },
            },
        ]
        result = _compute_cycle_times(task_groups)
        assert len(result) == 1
        assert result[0]["avg_cycle_days"] == 8.0

    def test_skips_groups_without_any_start_date(self) -> None:
        task_groups = [
            {
                "Id": 1,
                "DateActivated": None,
                "DateAdded": None,
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

    def test_skips_tasks_with_none_order(self) -> None:
        tasks = [
            {
                "Order": 1,
                "TaskName": "Step A",
                "DateActivated": "2026-01-01T00:00:00Z",
                "DateCompleted": "2026-01-02T00:00:00Z",
            },
            {
                "Order": None,
                "TaskName": "Unordered Task",
                "DateActivated": "2026-01-01T00:00:00Z",
                "DateCompleted": "2026-01-03T00:00:00Z",
            },
        ]

        result = _compute_step_durations(tasks)
        assert len(result) == 1
        assert result[0]["task_name"] == "Step A"

    def test_skips_steps_with_negative_duration(self) -> None:
        tasks = [
            {
                "Order": 1,
                "TaskName": "Step A",
                "DateActivated": "2026-01-01T00:00:00Z",
                "DateCompleted": "2026-01-02T00:00:00Z",
            },
            {
                "Order": 2,
                "TaskName": "Bad Data Step",
                "DateActivated": "2026-01-05T00:00:00Z",
                "DateCompleted": "2026-01-03T00:00:00Z",  # completed before activated
            },
        ]

        result = _compute_step_durations(tasks)
        assert len(result) == 1
        assert result[0]["task_name"] == "Step A"


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

    @respx.mock
    @pytest.mark.asyncio
    async def test_applies_plan_and_template_filters(self, client: PensionProClient) -> None:
        from urllib.parse import unquote

        route = respx.get("https://api.pensionpro.com/v2/taskgroups").mock(
            return_value=httpx.Response(200, json=[])
        )

        await get_task_group_cycle_times(
            client, days_back=30, plan_id=5, template_id=10
        )

        assert route.called
        url = unquote(str(route.calls[0].request.url))
        assert "Project/PlanId eq 5" in url
        assert "Project/ProjectTemplateId eq 10" in url

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
