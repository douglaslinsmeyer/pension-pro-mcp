"""Tests for worktray tools."""

import pytest
import respx
import httpx

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.worktrays import get_worktrays, get_worktray


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
        assert len(result["members"]) == 1
        assert len(result["active_tasks"]) == 2
