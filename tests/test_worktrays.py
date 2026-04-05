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
from pension_pro_mcp.tools.worktrays import _resolve_employee
from pension_pro_mcp.tools.worktrays import _compute_employee_workload
from pension_pro_mcp.tools.worktrays import _compute_employee_throughput
from pension_pro_mcp.tools.worktrays import _compute_employee_quality
from pension_pro_mcp.tools.worktrays import _compact_employee_segment
from pension_pro_mcp.tools.worktrays import get_employee_stats


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
        # Task 100: 24h, Task 101: 12h -> avg 18h, median 18h
        assert result["avg_completion_hours"] == 18.0
        assert result["median_completion_hours"] == 18.0
        # Task 100: 2h, Task 101: 1h -> avg 1.5h, median 1.5h
        assert result["avg_pickup_hours"] == 1.5
        assert result["median_pickup_hours"] == 1.5
        assert result["tasks_per_day"] == round(2 / 30, 2)

    def test_empty_tasks(self) -> None:
        result = _compute_employee_throughput([], days_back=30)
        assert result["tasks_completed"] == 0
        assert result["avg_completion_hours"] is None
        assert result["median_completion_hours"] is None
        assert result["avg_pickup_hours"] is None
        assert result["median_pickup_hours"] is None
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
        assert result["median_completion_hours"] is None
        assert result["avg_pickup_hours"] is None
        assert result["median_pickup_hours"] is None

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
        assert annual["median_completion_hours"] == 24.0
        filing = next(p for p in result["by_project"] if p["project"] == "5500 Filing")
        assert filing["tasks_completed"] == 1
        assert filing["avg_completion_hours"] == 6.0
        assert filing["median_completion_hours"] == 6.0


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

        # Mock worktray detail fetches
        respx.get("https://api.pensionpro.com/v2/worktrays/100").mock(
            return_value=httpx.Response(200, json={"Id": 100, "Name": "Compliance Review"})
        )
        respx.get("https://api.pensionpro.com/v2/worktrays/200").mock(
            return_value=httpx.Response(200, json={"Id": 200, "Name": "Filing Queue"})
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
        assert wt100["worktray_name"] == "Compliance Review"
        assert wt100["workload"]["active_task_count"] == 1
        assert wt100["throughput"]["tasks_completed"] == 1
        # Compact: no task_type_breakdown or by_project
        assert "task_type_breakdown" not in wt100["throughput"]
        assert "by_project" not in wt100["throughput"]
        assert "tasks" not in wt100["workload"]

        # Find worktray 200 segment (has 1 completed with bounce-back, 0 active)
        wt200 = next(s for s in result["worktray_segments"] if s["worktray_id"] == 200)
        assert wt200["worktray_name"] == "Filing Queue"
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
