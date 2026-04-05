"""Tests for worktray tools."""

from datetime import datetime, timezone

import pytest
import respx
import httpx

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.worktrays import get_worktrays, get_worktray
from pension_pro_mcp.tools.worktrays import _compute_workload_stats
from pension_pro_mcp.tools.worktrays import _compute_performance_stats
from pension_pro_mcp.tools.worktrays import _compute_queue_health
from pension_pro_mcp.tools.worktrays import get_worktray_member_stats


class TestGetWorktrays:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_worktrays(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/worktrays").mock(
            return_value=httpx.Response(200, json=[
                {"Id": 1, "Name": "Review Worktray", "IsActive": True},
                {"Id": 2, "Name": "Onboarding", "IsActive": True},
            ])
        )
        result = await get_worktrays(client)
        assert len(result) == 2
        assert result[0]["Name"] == "Review Worktray"


class TestGetWorktray:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_worktray_with_members_and_tasks(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/worktrays/100").mock(
            return_value=httpx.Response(200, json={"Id": 100, "Name": "Review Worktray"})
        )
        respx.get("https://api.pensionpro.com/v2/worktrayMembers").mock(
            return_value=httpx.Response(200, json=[
                {"Id": 1, "contactID": 500, "WorktrayID": 100, "RoleID": 1},
            ])
        )
        respx.get("https://api.pensionpro.com/v2/tasks").mock(
            return_value=httpx.Response(200, json=[
                {"Id": 10, "TaskName": "Initial Review", "TeamId": 100, "DateCompleted": None},
                {"Id": 11, "TaskName": "Final Review", "TeamId": 100, "DateCompleted": None},
            ])
        )
        result = await get_worktray(client, worktray_id=100)
        assert result["worktray"]["Name"] == "Review Worktray"
        assert result["member_count"] == 1
        assert len(result["members"]) == 1
        assert result["active_task_count"] == 2
        assert result["task_summary"]["by_type"][0]["task_name"] == "Initial Review"
        assert result["task_summary"]["by_type"][0]["count"] == 1


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
        assert len(result["overdue_by_type"]) == 1
        assert result["overdue_by_type"][0]["task_name"] == "Slow Task"
        assert result["overdue_by_type"][0]["count"] == 1
        assert result["overdue_by_type"][0]["avg_days_over_sla"] == 12  # 15 days old - 3 DaysToComp
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
        assert result["overdue_by_type"] == []


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
        assert result["member_count"] == 2
        assert len(result["top_members"]) == 2
        alice = next(m for m in result["top_members"] if m["contact_id"] == 500)
        assert alice["name"] == "Alice Smith"
        assert alice["workload"]["active_task_count"] == 1
        assert alice["performance"]["tasks_completed"] == 1
        assert "task_type_breakdown" not in alice["performance"]  # stripped in compact
        assert "tasks" not in alice["workload"]  # stripped in compact
        assert result["aggregate"]["workload"]["total_active"] == 1
        assert result["aggregate"]["performance"]["total_completed"] == 1
        assert "throughput_per_day" in result["aggregate"]["queue_health"]
        assert "overdue_tasks" not in result["aggregate"]["queue_health"]  # stripped in compact
        assert "overdue_by_type" in result["aggregate"]["queue_health"]
        assert "full_results" in result
        assert "resource_uri" in result

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

        assert result["top_members"] == []
        assert result["member_count"] == 0
        assert result["aggregate"]["workload"]["total_active"] == 0
        assert result["aggregate"]["performance"]["total_completed"] == 0
        assert result["aggregate"]["queue_health"]["throughput_per_day"] == 0.0
