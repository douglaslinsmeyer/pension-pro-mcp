"""Tests for notes tools."""

import pytest
import respx
import httpx

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.notes import add_note, get_notes


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> PensionProClient:
    monkeypatch.setenv("PENSION_PRO_API_KEY", "test-key")
    monkeypatch.setenv("PENSION_PRO_USERNAME", "test-user")
    return PensionProClient()


class TestAddNote:
    @respx.mock
    @pytest.mark.asyncio
    async def test_adds_note_to_plan(self, client: PensionProClient) -> None:
        respx.post("https://api.pensionpro.com/v2/notes").mock(
            return_value=httpx.Response(200, json={"Id": 1, "NoteText": "Test note"})
        )
        result = await add_note(client, text="Test note", plan_id=5)
        assert result["Id"] == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_adds_note_to_project(self, client: PensionProClient) -> None:
        respx.post("https://api.pensionpro.com/v2/notes").mock(
            return_value=httpx.Response(200, json={"Id": 2, "NoteText": "Project note"})
        )
        result = await add_note(client, text="Project note", project_id=10)
        assert result["Id"] == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_adds_note_to_task(self, client: PensionProClient) -> None:
        respx.post("https://api.pensionpro.com/v2/notes").mock(
            return_value=httpx.Response(200, json={"Id": 3})
        )
        result = await add_note(client, text="Task note", task_id=20)
        assert result["Id"] == 3

    @pytest.mark.asyncio
    async def test_raises_without_entity(self, client: PensionProClient) -> None:
        with pytest.raises(ValueError, match="At least one entity ID"):
            await add_note(client, text="Orphan note")

    @respx.mock
    @pytest.mark.asyncio
    async def test_adds_note_with_category(self, client: PensionProClient) -> None:
        respx.post("https://api.pensionpro.com/v2/notes").mock(
            return_value=httpx.Response(200, json={"Id": 4})
        )
        result = await add_note(client, text="Categorized", plan_id=1, category_id=3)
        assert result["Id"] == 4


class TestGetNotes:
    @respx.mock
    @pytest.mark.asyncio
    async def test_gets_notes_for_plan(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/plans/5/notes").mock(
            return_value=httpx.Response(200, json=[{"Id": 1, "NoteText": "Plan note"}])
        )
        result = await get_notes(client, plan_id=5)
        assert len(result) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_gets_notes_for_project(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/projects/10/notes").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await get_notes(client, project_id=10)
        assert result == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_gets_notes_for_task(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/tasks/20/notes").mock(
            return_value=httpx.Response(200, json=[{"Id": 5}])
        )
        result = await get_notes(client, task_id=20)
        assert len(result) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_gets_notes_for_contact(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/contacts/3/notes").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await get_notes(client, contact_id=3)
        assert result == []

    @pytest.mark.asyncio
    async def test_raises_without_entity(self, client: PensionProClient) -> None:
        with pytest.raises(ValueError, match="At least one entity ID"):
            await get_notes(client)
