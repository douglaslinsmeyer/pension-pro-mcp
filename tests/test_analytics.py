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
