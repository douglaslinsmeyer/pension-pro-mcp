"""Tests for project and task workflow tools."""

import pytest
import respx
import httpx

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.projects import (
    search_projects, get_project_details, complete_task,
    uncomplete_task, reassign_task, create_project_from_template,
)


class TestSearchProjects:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_projects(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/projects").mock(
            return_value=httpx.Response(200, json=[{"Id": 1, "Name": "Annual Filing"}])
        )
        result = await search_projects(client)
        assert len(result) == 1
        assert result[0]["Id"] == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_filters_by_plan_id(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/plans/5/projects").mock(
            return_value=httpx.Response(200, json=[{"Id": 10}])
        )
        result = await search_projects(client, plan_id=5)
        assert len(result) == 1


class TestGetProjectDetails:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_project_with_tasks_and_notes(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/projects/1").mock(
            return_value=httpx.Response(200, json={"Id": 1, "Name": "Filing"})
        )
        respx.get("https://api.pensionpro.com/v2/projects/1/taskgroups").mock(
            return_value=httpx.Response(200, json=[{"Id": 10, "Name": "Group A"}])
        )
        respx.get("https://api.pensionpro.com/v2/projects/1/tasks").mock(
            return_value=httpx.Response(200, json=[{"Id": 20, "CompletedOn": None}])
        )
        respx.get("https://api.pensionpro.com/v2/projects/1/participants").mock(
            return_value=httpx.Response(200, json=[])
        )
        respx.get("https://api.pensionpro.com/v2/projects/1/notes").mock(
            return_value=httpx.Response(200, json=[{"Id": 30, "NoteText": "hello"}])
        )
        result = await get_project_details(client, project_id=1)
        assert result["project"]["Id"] == 1
        assert len(result["task_groups"]) == 1
        assert len(result["tasks"]) == 1
        assert result["notes"][0]["NoteText"] == "hello"


class TestCompleteTask:
    @respx.mock
    @pytest.mark.asyncio
    async def test_completes_task(self, client: PensionProClient) -> None:
        respx.put("https://api.pensionpro.com/v2/tasks/42/completetask").mock(
            return_value=httpx.Response(200, json=True)
        )
        result = await complete_task(client, task_id=42)
        assert result is True


class TestUncompleteTask:
    @respx.mock
    @pytest.mark.asyncio
    async def test_uncompletes_task(self, client: PensionProClient) -> None:
        respx.put("https://api.pensionpro.com/v2/tasks/42/uncompletetask").mock(
            return_value=httpx.Response(200, json=True)
        )
        result = await uncomplete_task(client, task_id=42)
        assert result is True


class TestReassignTask:
    @respx.mock
    @pytest.mark.asyncio
    async def test_reassigns_task(self, client: PensionProClient) -> None:
        respx.put("https://api.pensionpro.com/v2/tasks/employee/42/99").mock(
            return_value=httpx.Response(200, json=True)
        )
        result = await reassign_task(client, task_id=42, assigned_to_id=99)
        assert result is True


class TestCreateProjectFromTemplate:
    @respx.mock
    @pytest.mark.asyncio
    async def test_creates_project(self, client: PensionProClient) -> None:
        respx.post("https://api.pensionpro.com/v2/projects").mock(
            return_value=httpx.Response(200, json={"Id": 200, "Name": "New Project"})
        )
        result = await create_project_from_template(client, plan_id=5, template_id=10)
        assert result["Id"] == 200
