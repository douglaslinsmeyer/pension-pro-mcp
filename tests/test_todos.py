"""Tests for to-do management tools."""

import pytest
import respx
import httpx

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.todos import search_todos, get_todo, create_todo, update_todo


class TestSearchTodos:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_todos(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/todos").mock(
            return_value=httpx.Response(200, json=[{"Id": 1, "ToDoName": "Review filing"}])
        )
        result = await search_todos(client)
        assert len(result) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_filters_by_plan_id(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/plans/5/todos").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await search_todos(client, plan_id=5)
        assert result == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_filters_by_project_id(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/projects/10/todos").mock(
            return_value=httpx.Response(200, json=[{"Id": 2}])
        )
        result = await search_todos(client, project_id=10)
        assert len(result) == 1


class TestGetTodo:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_todo_with_comments(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/todos/1").mock(
            return_value=httpx.Response(200, json={
                "Id": 1, "ToDoName": "Review",
                "ToDoLink": {"EntityId": 5, "EntityTypeId": 1},
            })
        )
        respx.get("https://api.pensionpro.com/v2/todos/1/todocomments").mock(
            return_value=httpx.Response(200, json=[{"Id": 10, "CommentText": "Done"}])
        )
        result = await get_todo(client, todo_id=1)
        assert result["todo"]["ToDoName"] == "Review"
        assert len(result["comments"]) == 1
        assert result["link"]["EntityId"] == 5


class TestCreateTodo:
    @respx.mock
    @pytest.mark.asyncio
    async def test_creates_todo_with_plan_link(self, client: PensionProClient) -> None:
        respx.post("https://api.pensionpro.com/v2/todos").mock(
            return_value=httpx.Response(200, json={"Id": 50, "ToDoName": "New task"})
        )
        result = await create_todo(client, subject="New task", plan_id=5)
        assert result["Id"] == 50

    @respx.mock
    @pytest.mark.asyncio
    async def test_creates_todo_with_project_link(self, client: PensionProClient) -> None:
        respx.post("https://api.pensionpro.com/v2/todos").mock(
            return_value=httpx.Response(200, json={"Id": 51})
        )
        result = await create_todo(client, subject="Task", project_id=10)
        assert result["Id"] == 51


class TestUpdateTodo:
    @respx.mock
    @pytest.mark.asyncio
    async def test_updates_todo(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/todos/5").mock(
            return_value=httpx.Response(200, json={
                "Id": 5, "ToDoName": "Old name", "DataKey": "abc",
                "ToDoStatusId": 1, "PriorityId": 1, "Description": "",
                "DueOn": None, "AssignedToContactId": 0, "AssignedToTeamId": 0,
                "CompletedOn": None, "StartedOn": None, "PercentageCompleted": 0,
                "HasBeenWarned": False, "IsDeactivated": False,
            })
        )
        respx.put("https://api.pensionpro.com/v2/todos/5").mock(
            return_value=httpx.Response(200, json={"Id": 5, "ToDoName": "New name"})
        )
        result = await update_todo(client, todo_id=5, subject="New name")
        assert result["ToDoName"] == "New name"
