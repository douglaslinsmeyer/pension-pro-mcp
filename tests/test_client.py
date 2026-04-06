"""Tests for the PensionPro API client."""

import asyncio
import time

import pytest
import respx
import httpx

from pension_pro_mcp.client import PensionProClient, PensionProError, RateLimiter


class TestClientInit:
    def test_raises_when_missing_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PENSION_PRO_API_KEY", raising=False)
        monkeypatch.delenv("PENSION_PRO_USERNAME", raising=False)
        with pytest.raises(ValueError, match="PENSION_PRO_API_KEY"):
            PensionProClient()

    def test_sets_auth_headers(self, client: PensionProClient) -> None:
        assert client._http.headers["apikey"] == "test-key"
        assert client._http.headers["username"] == "test-user"


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
        import json
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body == {"NoteText": "hello"}


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


class TestODataQuery:
    def test_builds_filter_with_eq(self, client: PensionProClient) -> None:
        params = client.build_odata_params(
            filters={"Name": "Acme 401k"},
            top=50,
        )
        assert params["$filter"] == "Name eq 'Acme 401k'"
        assert params["$top"] == "50"

    def test_builds_filter_with_contains(self, client: PensionProClient) -> None:
        params = client.build_odata_params(
            filters={"Name__contains": "Acme"},
        )
        assert params["$filter"] == "contains(Name, 'Acme')"

    def test_builds_multiple_filters(self, client: PensionProClient) -> None:
        params = client.build_odata_params(
            filters={"Name__contains": "Acme", "IsDeactivated": "false"},
        )
        assert "contains(Name, 'Acme')" in params["$filter"]
        assert "IsDeactivated eq false" in params["$filter"]
        assert " and " in params["$filter"]

    def test_builds_orderby(self, client: PensionProClient) -> None:
        params = client.build_odata_params(orderby="Name desc")
        assert params["$orderby"] == "Name desc"

    def test_builds_expand(self, client: PensionProClient) -> None:
        params = client.build_odata_params(expand=["Client", "PlanType"])
        assert params["$expand"] == "Client,PlanType"

    def test_builds_skip(self, client: PensionProClient) -> None:
        params = client.build_odata_params(skip=100, top=50)
        assert params["$skip"] == "100"
        assert params["$top"] == "50"

    def test_builds_filter_with_ge(self, client: PensionProClient) -> None:
        params = client.build_odata_params(
            filters={"DateCompleted__ge": "2026-03-05T00:00:00Z"},
        )
        assert params["$filter"] == "DateCompleted ge '2026-03-05T00:00:00Z'"

    def test_builds_filter_with_le(self, client: PensionProClient) -> None:
        params = client.build_odata_params(
            filters={"DateCompleted__le": "2026-04-04T00:00:00Z"},
        )
        assert params["$filter"] == "DateCompleted le '2026-04-04T00:00:00Z'"

    def test_builds_filter_with_gt(self, client: PensionProClient) -> None:
        params = client.build_odata_params(
            filters={"CompletedOn__gt": "2026-04-01T00:00:00Z"},
        )
        assert params["$filter"] == 'CompletedOn gt "2026-04-01T00:00:00Z"'

    def test_builds_filter_with_lt(self, client: PensionProClient) -> None:
        params = client.build_odata_params(
            filters={"CompletedOn__lt": "2026-04-01T00:00:00Z"},
        )
        assert params["$filter"] == 'CompletedOn lt "2026-04-01T00:00:00Z"'

    def test_empty_params_returns_empty_dict(self, client: PensionProClient) -> None:
        params = client.build_odata_params()
        assert params == {}


class TestGetList:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get_list_returns_results(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/plans").mock(
            return_value=httpx.Response(200, json=[
                {"Id": 1, "Name": "Plan A"},
                {"Id": 2, "Name": "Plan B"},
            ])
        )
        results = await client.get_list("/plans", top=50)
        assert len(results) == 2
        assert results[0]["Name"] == "Plan A"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_list_paginates(self, client: PensionProClient) -> None:
        route = respx.get("https://api.pensionpro.com/v2/plans")
        route.side_effect = [
            httpx.Response(200, json=[{"Id": 1}, {"Id": 2}]),
            httpx.Response(200, json=[{"Id": 3}]),
        ]
        results = await client.get_list("/plans", top=2)
        assert len(results) == 3
        second_request = route.calls[1].request
        assert "$skip=2" in str(second_request.url)

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_list_respects_limit(self, client: PensionProClient) -> None:
        route = respx.get("https://api.pensionpro.com/v2/plans")
        route.side_effect = [
            httpx.Response(200, json=[{"Id": i} for i in range(1000)]),
            httpx.Response(200, json=[{"Id": i} for i in range(1000, 2000)]),
        ]
        results = await client.get_list("/plans", top=1000, max_total=1500)
        assert len(results) == 1500

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_list_with_filters(self, client: PensionProClient) -> None:
        route = respx.get("https://api.pensionpro.com/v2/plans").mock(
            return_value=httpx.Response(200, json=[{"Id": 1}])
        )
        await client.get_list("/plans", filters={"Name__contains": "Acme"}, top=50)
        request_url = str(route.calls[0].request.url)
        assert "contains(Name" in request_url


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_no_delay_when_remaining_is_healthy(self) -> None:
        rl = RateLimiter()
        rl.update(limit=100, remaining=80)
        start = time.monotonic()
        await rl.wait_if_needed()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05

    @pytest.mark.asyncio
    async def test_delays_when_remaining_is_low(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept: list[float] = []

        async def fake_sleep(delay: float) -> None:
            slept.append(delay)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        rl = RateLimiter()
        rl.update(limit=100, remaining=5)
        await rl.wait_if_needed()
        assert slept == [12.0]

    @pytest.mark.asyncio
    async def test_delays_when_remaining_is_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        slept: list[float] = []

        async def fake_sleep(delay: float) -> None:
            slept.append(delay)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        rl = RateLimiter()
        rl.update(limit=100, remaining=0)
        rl._window_start = time.monotonic() - 55.0
        await rl.wait_if_needed()
        assert len(slept) == 1
        assert 4.0 <= slept[0] <= 6.0

    @pytest.mark.asyncio
    async def test_window_resets_when_remaining_increases(self) -> None:
        rl = RateLimiter()
        rl.update(limit=100, remaining=50)
        rl._window_start -= 30.0
        old_window = rl._window_start
        # remaining jumps up — new window detected
        rl.update(limit=100, remaining=90)
        assert rl._window_start > old_window

    @pytest.mark.asyncio
    async def test_window_does_not_reset_when_remaining_decreases(self) -> None:
        rl = RateLimiter()
        rl.update(limit=100, remaining=50)
        rl._window_start -= 30.0
        old_window = rl._window_start
        rl.update(limit=100, remaining=40)
        assert rl._window_start == old_window

    @pytest.mark.asyncio
    async def test_defaults_allow_requests_before_first_response(self) -> None:
        rl = RateLimiter()
        # No update() called yet — should not delay
        start = time.monotonic()
        await rl.wait_if_needed()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05
