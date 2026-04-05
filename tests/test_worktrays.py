"""Tests for worktray tools."""

from datetime import datetime, timezone

import pytest
import respx
import httpx

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.worktrays import get_worktrays, get_worktray
from pension_pro_mcp.tools.worktrays import _compute_workload_stats


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

    def test_task_age_uses_task_active_over_date_added(self) -> None:
        members = [
            {"contactID": 1, "RoleID": 10, "Contact": {"FirstName": "A", "LastName": "B"}},
        ]
        active_tasks = [
            {
                "Id": 100, "TaskName": "Review", "AssignedToId": 1,
                "TaskActive": "2026-04-02T00:00:00Z", "DateAdded": "2026-03-01T00:00:00Z",
                "TaskGroup": {"Name": "G", "Project": {"Name": "P", "Id": 1}},
            },
        ]
        result = _compute_workload_stats(active_tasks, members, now=datetime(2026, 4, 4, tzinfo=timezone.utc))
        task = result["members"][0]["workload"]["tasks"][0]
        assert task["age_days"] == 2  # from TaskActive, not DateAdded
