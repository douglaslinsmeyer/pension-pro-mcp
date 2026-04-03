"""Tests for the PensionPro API client."""

import pytest
import respx
import httpx

from pension_pro_mcp.client import PensionProClient, PensionProError


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> PensionProClient:
    monkeypatch.setenv("PENSION_PRO_API_KEY", "test-key")
    monkeypatch.setenv("PENSION_PRO_USERNAME", "test-user")
    return PensionProClient()


class TestClientInit:
    def test_raises_when_missing_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PENSION_PRO_API_KEY", raising=False)
        monkeypatch.delenv("PENSION_PRO_USERNAME", raising=False)
        with pytest.raises(ValueError, match="PENSION_PRO_API_KEY"):
            PensionProClient()

    def test_sets_auth_header(self, client: PensionProClient) -> None:
        assert client._http.headers["apikey-username"] == "test-key|test-user"


class TestGet:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get_returns_json(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/plans/1").mock(
            return_value=httpx.Response(200, json={"Id": 1, "Name": "Test Plan"})
        )
        result = await client.get("/plans/1")
        assert result == {"Id": 1, "Name": "Test Plan"}

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_raises_on_error(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/plans/999").mock(
            return_value=httpx.Response(404, json={"Message": "Not found"})
        )
        with pytest.raises(PensionProError) as exc_info:
            await client.get("/plans/999")
        assert exc_info.value.status_code == 404
        assert "Not found" in exc_info.value.message

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_raises_on_non_json_error(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/plans/999").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        with pytest.raises(PensionProError) as exc_info:
            await client.get("/plans/999")
        assert exc_info.value.status_code == 500


class TestPost:
    @respx.mock
    @pytest.mark.asyncio
    async def test_post_sends_json_body(self, client: PensionProClient) -> None:
        route = respx.post("https://api.pensionpro.com/v2/notes").mock(
            return_value=httpx.Response(200, json={"Id": 10})
        )
        result = await client.post("/notes", data={"NoteText": "hello"})
        assert result == {"Id": 10}
        assert route.calls[0].request.content == b'{"NoteText": "hello"}'


class TestPut:
    @respx.mock
    @pytest.mark.asyncio
    async def test_put_sends_json_body(self, client: PensionProClient) -> None:
        respx.put("https://api.pensionpro.com/v2/todos/5").mock(
            return_value=httpx.Response(200, json={"Id": 5})
        )
        result = await client.put("/todos/5", data={"ToDoName": "updated"})
        assert result == {"Id": 5}

    @respx.mock
    @pytest.mark.asyncio
    async def test_put_without_body(self, client: PensionProClient) -> None:
        respx.put("https://api.pensionpro.com/v2/tasks/1/completetask").mock(
            return_value=httpx.Response(200, json=True)
        )
        result = await client.put("/tasks/1/completetask")
        assert result is True


class TestDelete:
    @respx.mock
    @pytest.mark.asyncio
    async def test_delete(self, client: PensionProClient) -> None:
        respx.delete("https://api.pensionpro.com/v2/notes/3").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        result = await client.delete("/notes/3")
        assert result == {"success": True}
