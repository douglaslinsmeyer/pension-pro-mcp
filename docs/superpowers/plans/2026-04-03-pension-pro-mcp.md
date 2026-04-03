# PensionPro MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python MCP server that wraps the PensionPro REST API v2 into 18 domain-oriented tools for plan lookup, project/task workflow, client search, to-do management, and notes.

**Architecture:** FastMCP server with a shared `httpx.AsyncClient` managed via lifespan. An `PensionProClient` class handles auth, OData query building, pagination, and error handling. Tool modules register domain-oriented tools that aggregate multiple API calls into useful responses.

**Tech Stack:** Python 3.12+, `mcp` SDK (FastMCP), `httpx`, `pytest`, `pytest-asyncio`, `respx`, `hatchling`

**Spec:** `docs/superpowers/specs/2026-04-03-pension-pro-mcp-design.md`

---

## File Structure

```
pension-pro-mcp/
├── src/
│   └── pension_pro_mcp/
│       ├── __init__.py            # Package init, version
│       ├── server.py              # FastMCP server, lifespan, tool registration
│       ├── client.py              # PensionProClient: auth, HTTP, OData, pagination
│       └── tools/
│           ├── __init__.py        # Re-exports register functions
│           ├── plans.py           # search_plans, get_plan_details, get_plan_projects
│           ├── projects.py        # search_projects, get_project_details, complete_task, uncomplete_task, reassign_task, create_project_from_template
│           ├── clients.py         # search_clients, get_client_details, search_contacts
│           ├── todos.py           # search_todos, get_todo, create_todo, update_todo
│           └── notes.py           # add_note, get_notes
├── tests/
│   ├── conftest.py                # Shared fixtures: mock PensionProClient, respx routes
│   ├── test_client.py             # API client unit tests
│   ├── test_plans.py              # Plan tool tests
│   ├── test_projects.py           # Project/task tool tests
│   ├── test_clients.py            # Client/contact tool tests
│   ├── test_todos.py              # Todo tool tests
│   └── test_notes.py              # Notes tool tests
├── pyproject.toml
├── README.md
└── LICENSE
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/pension_pro_mcp/__init__.py`
- Create: `src/pension_pro_mcp/server.py`
- Create: `src/pension_pro_mcp/client.py`
- Create: `src/pension_pro_mcp/tools/__init__.py`
- Create: `tests/conftest.py`
- Create: `LICENSE`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pension-pro-mcp"
version = "0.1.0"
description = "MCP server for the PensionPro API"
readme = "README.md"
license = "MIT"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0.0",
    "httpx>=0.27.0",
]

[project.scripts]
pension-pro-mcp = "pension_pro_mcp.server:main"

[tool.hatch.build.targets.wheel]
packages = ["src/pension_pro_mcp"]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
]
```

- [ ] **Step 2: Create LICENSE**

```
MIT License

Copyright (c) 2026 Douglas Linsmeyer

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: Create package init**

`src/pension_pro_mcp/__init__.py`:
```python
"""PensionPro MCP Server - Domain-oriented MCP tools for the PensionPro API."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Create stub server.py**

`src/pension_pro_mcp/server.py`:
```python
"""PensionPro MCP Server entry point."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from pension_pro_mcp.client import PensionProClient


@dataclass
class AppContext:
    """Shared application context available to all tools."""

    client: PensionProClient


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage the PensionPro HTTP client lifecycle."""
    client = PensionProClient()
    try:
        yield AppContext(client=client)
    finally:
        await client.close()


mcp = FastMCP(
    "PensionPro",
    lifespan=app_lifespan,
)


def main() -> None:
    """CLI entry point."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Create stub client.py**

`src/pension_pro_mcp/client.py`:
```python
"""PensionPro API client."""

import os

import httpx


class PensionProError(Exception):
    """Raised when the PensionPro API returns an error."""

    def __init__(self, status_code: int, message: str, endpoint: str) -> None:
        self.status_code = status_code
        self.message = message
        self.endpoint = endpoint
        super().__init__(f"PensionPro API error {status_code} on {endpoint}: {message}")


class PensionProClient:
    """Async HTTP client for the PensionPro REST API v2."""

    BASE_URL = "https://api.pensionpro.com/v2"

    def __init__(self) -> None:
        api_key = os.environ.get("PENSION_PRO_API_KEY", "")
        username = os.environ.get("PENSION_PRO_USERNAME", "")
        if not api_key or not username:
            raise ValueError(
                "PENSION_PRO_API_KEY and PENSION_PRO_USERNAME environment variables are required"
            )
        self._http = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"apikey-username": f"{api_key}|{username}"},
            timeout=30.0,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()
```

- [ ] **Step 6: Create tools/__init__.py**

`src/pension_pro_mcp/tools/__init__.py`:
```python
"""PensionPro MCP tool modules."""
```

- [ ] **Step 7: Create tests/conftest.py stub**

`tests/conftest.py`:
```python
"""Shared test fixtures."""

import pytest
```

- [ ] **Step 8: Install dependencies and verify**

Run: `cd /home/douglasl/Projects/pension-pro-mcp && uv init --no-readme 2>/dev/null; uv pip install -e ".[dev]" 2>&1 || pip install -e ".[dev]"`
Expected: Dependencies installed successfully.

Run: `python -c "from pension_pro_mcp import __version__; print(__version__)"`
Expected: `0.1.0`

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml LICENSE src/ tests/conftest.py
git commit -m "feat: scaffold project with FastMCP server, stub client, and packaging"
```

---

### Task 2: PensionPro API Client — Core HTTP Methods

**Files:**
- Modify: `src/pension_pro_mcp/client.py`
- Create: `tests/test_client.py`

- [ ] **Step 1: Write failing tests for GET and error handling**

`tests/test_client.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_client.py -v`
Expected: FAIL — `get`, `post`, `put`, `delete` methods not defined on `PensionProClient`.

- [ ] **Step 3: Implement core HTTP methods**

Add to `src/pension_pro_mcp/client.py` inside the `PensionProClient` class, after the `close` method:

```python
    async def _handle_response(self, response: httpx.Response, endpoint: str) -> Any:
        """Check response status and return parsed JSON."""
        if response.status_code >= 400:
            try:
                body = response.json()
                message = body.get("Message", str(body))
            except Exception:
                message = response.text or f"HTTP {response.status_code}"
            raise PensionProError(response.status_code, message, endpoint)
        return response.json()

    async def get(self, endpoint: str, params: dict[str, str] | None = None) -> Any:
        """Send a GET request."""
        response = await self._http.get(endpoint, params=params)
        return await self._handle_response(response, endpoint)

    async def post(self, endpoint: str, data: dict[str, Any] | None = None) -> Any:
        """Send a POST request with a JSON body."""
        response = await self._http.post(endpoint, json=data)
        return await self._handle_response(response, endpoint)

    async def put(self, endpoint: str, data: dict[str, Any] | None = None) -> Any:
        """Send a PUT request with an optional JSON body."""
        response = await self._http.put(endpoint, json=data)
        return await self._handle_response(response, endpoint)

    async def delete(self, endpoint: str) -> Any:
        """Send a DELETE request."""
        response = await self._http.delete(endpoint)
        return await self._handle_response(response, endpoint)
```

Also add `from typing import Any` to the top of `client.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_client.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pension_pro_mcp/client.py tests/test_client.py
git commit -m "feat: add core HTTP methods (get, post, put, delete) to PensionProClient"
```

---

### Task 3: PensionPro API Client — OData Query Builder & Pagination

**Files:**
- Modify: `src/pension_pro_mcp/client.py`
- Modify: `tests/test_client.py`

- [ ] **Step 1: Write failing tests for OData query building**

Add to `tests/test_client.py`:

```python
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
        # Both filters should be joined with 'and'
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

    def test_empty_params_returns_empty_dict(self, client: PensionProClient) -> None:
        params = client.build_odata_params()
        assert params == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_client.py::TestODataQuery -v`
Expected: FAIL — `build_odata_params` not defined.

- [ ] **Step 3: Implement OData query builder**

Add to `PensionProClient` class in `src/pension_pro_mcp/client.py`:

```python
    def build_odata_params(
        self,
        filters: dict[str, str] | None = None,
        expand: list[str] | None = None,
        orderby: str | None = None,
        top: int | None = None,
        skip: int | None = None,
    ) -> dict[str, str]:
        """Build OData query parameters from structured inputs."""
        params: dict[str, str] = {}

        if filters:
            clauses: list[str] = []
            for key, value in filters.items():
                if key.endswith("__contains"):
                    field = key[: -len("__contains")]
                    clauses.append(f"contains({field}, '{value}')")
                elif value in ("true", "false"):
                    clauses.append(f"{key} eq {value}")
                else:
                    clauses.append(f"{key} eq '{value}'")
            params["$filter"] = " and ".join(clauses)

        if expand:
            params["$expand"] = ",".join(expand)

        if orderby:
            params["$orderby"] = orderby

        if top is not None:
            params["$top"] = str(top)

        if skip is not None:
            params["$skip"] = str(skip)

        return params
```

- [ ] **Step 4: Run OData tests to verify they pass**

Run: `pytest tests/test_client.py::TestODataQuery -v`
Expected: All PASS.

- [ ] **Step 5: Write failing tests for list (paginated) endpoint**

Add to `tests/test_client.py`:

```python
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
        # First page returns 2 items (matching page size), second returns 1 (less than page size = done)
        route = respx.get("https://api.pensionpro.com/v2/plans")
        route.side_effect = [
            httpx.Response(200, json=[{"Id": 1}, {"Id": 2}]),
            httpx.Response(200, json=[{"Id": 3}]),
        ]
        results = await client.get_list("/plans", top=2)
        assert len(results) == 3
        # Verify second call included $skip
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
```

- [ ] **Step 6: Run pagination tests to verify they fail**

Run: `pytest tests/test_client.py::TestGetList -v`
Expected: FAIL — `get_list` not defined.

- [ ] **Step 7: Implement get_list with pagination**

Add to `PensionProClient` class:

```python
    async def get_list(
        self,
        endpoint: str,
        filters: dict[str, str] | None = None,
        expand: list[str] | None = None,
        orderby: str | None = None,
        top: int = 1000,
        max_total: int = 5000,
    ) -> list[dict[str, Any]]:
        """Fetch a list endpoint with automatic pagination.

        Args:
            endpoint: API endpoint path (e.g., "/plans").
            filters: OData filter parameters.
            expand: Related entities to expand.
            orderby: Sort expression.
            top: Page size (max 1000 per API limit).
            max_total: Maximum total results to fetch across all pages.
        """
        page_size = min(top, 1000)
        all_results: list[dict[str, Any]] = []
        skip = 0

        while len(all_results) < max_total:
            params = self.build_odata_params(
                filters=filters,
                expand=expand,
                orderby=orderby,
                top=page_size,
                skip=skip if skip > 0 else None,
            )
            page = await self.get(endpoint, params=params)
            if not isinstance(page, list):
                page = [page]

            all_results.extend(page)

            if len(page) < page_size:
                break

            skip += page_size

        return all_results[:max_total]
```

- [ ] **Step 8: Run all client tests**

Run: `pytest tests/test_client.py -v`
Expected: All PASS.

- [ ] **Step 9: Commit**

```bash
git add src/pension_pro_mcp/client.py tests/test_client.py
git commit -m "feat: add OData query builder and paginated list fetching to client"
```

---

### Task 4: Plan Tools

**Files:**
- Create: `src/pension_pro_mcp/tools/plans.py`
- Create: `tests/test_plans.py`
- Modify: `src/pension_pro_mcp/server.py`

- [ ] **Step 1: Write failing tests for search_plans**

`tests/test_plans.py`:
```python
"""Tests for plan tools."""

import pytest
import respx
import httpx

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.plans import search_plans, get_plan_details, get_plan_projects


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> PensionProClient:
    monkeypatch.setenv("PENSION_PRO_API_KEY", "test-key")
    monkeypatch.setenv("PENSION_PRO_USERNAME", "test-user")
    return PensionProClient()


class TestSearchPlans:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_plan_summaries(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/plans").mock(
            return_value=httpx.Response(200, json=[
                {"Id": 1, "Name": "Acme 401k", "InternalPlanId": "ACM-001"},
                {"Id": 2, "Name": "Beta Plan", "InternalPlanId": "BET-001"},
            ])
        )
        result = await search_plans(client, name="Acme")
        assert len(result) == 2
        assert result[0]["Id"] == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_applies_name_filter(self, client: PensionProClient) -> None:
        route = respx.get("https://api.pensionpro.com/v2/plans").mock(
            return_value=httpx.Response(200, json=[])
        )
        await search_plans(client, name="Acme")
        request_url = str(route.calls[0].request.url)
        assert "contains(Name" in request_url or "contains(SearchText" in request_url


class TestGetPlanDetails:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_plan_with_related_data(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/plans/1").mock(
            return_value=httpx.Response(200, json={"Id": 1, "Name": "Acme 401k"})
        )
        respx.get("https://api.pensionpro.com/v2/plans/1/plancontactroles").mock(
            return_value=httpx.Response(200, json=[{"Id": 10, "ContactName": "Jane"}])
        )
        respx.get("https://api.pensionpro.com/v2/plans/1/planCycles").mock(
            return_value=httpx.Response(200, json=[{"Id": 20}])
        )
        respx.get("https://api.pensionpro.com/v2/plans/1/planServicesProvidedLinks").mock(
            return_value=httpx.Response(200, json=[])
        )
        respx.get("https://api.pensionpro.com/v2/plans/1/investmentproviders").mock(
            return_value=httpx.Response(200, json=[])
        )
        respx.get("https://api.pensionpro.com/v2/plans/1/feeschedules").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await get_plan_details(client, plan_id=1)
        assert result["plan"]["Id"] == 1
        assert result["contacts"][0]["ContactName"] == "Jane"
        assert len(result["plan_cycles"]) == 1


class TestGetPlanProjects:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_projects_with_task_summary(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/plans/1/projects").mock(
            return_value=httpx.Response(200, json=[
                {"Id": 100, "Name": "Annual Filing", "ProjectStatusId": 1},
            ])
        )
        respx.get("https://api.pensionpro.com/v2/projects/100/tasks").mock(
            return_value=httpx.Response(200, json=[
                {"Id": 1, "CompletedOn": "2026-01-01T00:00:00"},
                {"Id": 2, "CompletedOn": None},
                {"Id": 3, "CompletedOn": None},
            ])
        )
        result = await get_plan_projects(client, plan_id=1)
        assert len(result) == 1
        assert result[0]["project"]["Id"] == 100
        assert result[0]["task_summary"]["total"] == 3
        assert result[0]["task_summary"]["completed"] == 1
        assert result[0]["task_summary"]["pending"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plans.py -v`
Expected: FAIL — cannot import `search_plans`, `get_plan_details`, `get_plan_projects`.

- [ ] **Step 3: Implement plan tools**

`src/pension_pro_mcp/tools/plans.py`:
```python
"""Plan lookup and search tools."""

from typing import Any

from pension_pro_mcp.client import PensionProClient


async def search_plans(
    client: PensionProClient,
    name: str | None = None,
    status: str | None = None,
    plan_type: str | None = None,
    client_name: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search and filter plans."""
    filters: dict[str, str] = {}
    if name:
        filters["SearchText__contains"] = name
    if status:
        filters["Status.DisplayName"] = status
    if plan_type:
        filters["PlanType.DisplayName"] = plan_type
    if client_name:
        filters["Client.CompanyNameId__contains"] = client_name

    return await client.get_list("/plans", filters=filters, top=limit, max_total=limit)


async def get_plan_details(
    client: PensionProClient,
    plan_id: int,
) -> dict[str, Any]:
    """Get comprehensive details for a single plan."""
    plan = await client.get(f"/plans/{plan_id}")
    contacts = await client.get(f"/plans/{plan_id}/plancontactroles")
    plan_cycles = await client.get(f"/plans/{plan_id}/planCycles")
    services = await client.get(f"/plans/{plan_id}/planServicesProvidedLinks")
    investments = await client.get(f"/plans/{plan_id}/investmentproviders")
    fee_schedules = await client.get(f"/plans/{plan_id}/feeschedules")

    return {
        "plan": plan,
        "contacts": contacts if isinstance(contacts, list) else [contacts],
        "plan_cycles": plan_cycles if isinstance(plan_cycles, list) else [plan_cycles],
        "services_provided": services if isinstance(services, list) else [services],
        "investment_providers": investments if isinstance(investments, list) else [investments],
        "fee_schedules": fee_schedules if isinstance(fee_schedules, list) else [fee_schedules],
    }


async def get_plan_projects(
    client: PensionProClient,
    plan_id: int,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Get all projects for a plan with task completion summaries."""
    filters: dict[str, str] = {}
    if status:
        filters["ProjectStatus.DisplayName"] = status

    projects = await client.get_list(
        f"/plans/{plan_id}/projects", filters=filters, top=100, max_total=500
    )

    results: list[dict[str, Any]] = []
    for project in projects:
        project_id = project["Id"]
        tasks_data = await client.get(f"/projects/{project_id}/tasks")
        tasks = tasks_data if isinstance(tasks_data, list) else [tasks_data]
        completed = sum(1 for t in tasks if t.get("CompletedOn"))
        total = len(tasks)

        results.append({
            "project": project,
            "task_summary": {
                "total": total,
                "completed": completed,
                "pending": total - completed,
            },
        })

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_plans.py -v`
Expected: All PASS.

- [ ] **Step 5: Register plan tools on the MCP server**

Update `src/pension_pro_mcp/server.py` — add the tool registrations after the `mcp` instance creation:

```python
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from pension_pro_mcp.tools.plans import search_plans, get_plan_details, get_plan_projects


@mcp.tool()
async def search_plans_tool(
    ctx: Context[ServerSession, AppContext],
    name: str | None = None,
    status: str | None = None,
    plan_type: str | None = None,
    client_name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search and filter pension plans by name, status, type, or client.

    Returns a summary list of matching plans.
    """
    client = ctx.request_context.lifespan_context.client
    return await search_plans(client, name=name, status=status, plan_type=plan_type, client_name=client_name, limit=limit)


@mcp.tool()
async def get_plan_details_tool(
    ctx: Context[ServerSession, AppContext],
    plan_id: int,
) -> dict:
    """Get comprehensive details for a single plan.

    Returns the plan record with contacts, cycles, services, investments, and fee schedules.
    """
    client = ctx.request_context.lifespan_context.client
    return await get_plan_details(client, plan_id=plan_id)


@mcp.tool()
async def get_plan_projects_tool(
    ctx: Context[ServerSession, AppContext],
    plan_id: int,
    status: str | None = None,
) -> list[dict]:
    """Get all projects for a plan with task completion summaries.

    Each project includes a task_summary with total, completed, and pending counts.
    """
    client = ctx.request_context.lifespan_context.client
    return await get_plan_projects(client, plan_id=plan_id, status=status)
```

- [ ] **Step 6: Commit**

```bash
git add src/pension_pro_mcp/tools/plans.py src/pension_pro_mcp/server.py tests/test_plans.py
git commit -m "feat: add plan tools (search_plans, get_plan_details, get_plan_projects)"
```

---

### Task 5: Project & Task Workflow Tools

**Files:**
- Create: `src/pension_pro_mcp/tools/projects.py`
- Create: `tests/test_projects.py`
- Modify: `src/pension_pro_mcp/server.py`

- [ ] **Step 1: Write failing tests for project and task tools**

`tests/test_projects.py`:
```python
"""Tests for project and task workflow tools."""

import pytest
import respx
import httpx

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.projects import (
    search_projects,
    get_project_details,
    complete_task,
    uncomplete_task,
    reassign_task,
    create_project_from_template,
)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> PensionProClient:
    monkeypatch.setenv("PENSION_PRO_API_KEY", "test-key")
    monkeypatch.setenv("PENSION_PRO_USERNAME", "test-user")
    return PensionProClient()


class TestSearchProjects:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_projects(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/projects").mock(
            return_value=httpx.Response(200, json=[
                {"Id": 1, "Name": "Annual Filing"},
            ])
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
            return_value=httpx.Response(200, json=[
                {"Id": 20, "CompletedOn": None},
            ])
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
        route = respx.post("https://api.pensionpro.com/v2/projects").mock(
            return_value=httpx.Response(200, json={"Id": 200, "Name": "New Project"})
        )
        result = await create_project_from_template(client, plan_id=5, template_id=10)
        assert result["Id"] == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_projects.py -v`
Expected: FAIL — cannot import from `pension_pro_mcp.tools.projects`.

- [ ] **Step 3: Implement project and task tools**

`src/pension_pro_mcp/tools/projects.py`:
```python
"""Project and task workflow tools."""

from typing import Any

from pension_pro_mcp.client import PensionProClient


async def search_projects(
    client: PensionProClient,
    status: str | None = None,
    project_type: str | None = None,
    plan_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search and filter projects."""
    filters: dict[str, str] = {}
    if status:
        filters["ProjectStatus.DisplayName"] = status
    if project_type:
        filters["ProjectType.DisplayName"] = project_type

    endpoint = f"/plans/{plan_id}/projects" if plan_id else "/projects"
    return await client.get_list(endpoint, filters=filters, top=limit, max_total=limit)


async def get_project_details(
    client: PensionProClient,
    project_id: int,
) -> dict[str, Any]:
    """Get a project with full task and participant details."""
    project = await client.get(f"/projects/{project_id}")
    task_groups = await client.get(f"/projects/{project_id}/taskgroups")
    tasks = await client.get(f"/projects/{project_id}/tasks")
    participants = await client.get(f"/projects/{project_id}/participants")
    notes = await client.get(f"/projects/{project_id}/notes")

    return {
        "project": project,
        "task_groups": task_groups if isinstance(task_groups, list) else [task_groups],
        "tasks": tasks if isinstance(tasks, list) else [tasks],
        "participants": participants if isinstance(participants, list) else [participants],
        "notes": notes if isinstance(notes, list) else [notes],
    }


async def complete_task(
    client: PensionProClient,
    task_id: int,
) -> Any:
    """Mark a task as complete."""
    return await client.put(f"/tasks/{task_id}/completetask")


async def uncomplete_task(
    client: PensionProClient,
    task_id: int,
) -> Any:
    """Undo task completion."""
    return await client.put(f"/tasks/{task_id}/uncompletetask")


async def reassign_task(
    client: PensionProClient,
    task_id: int,
    assigned_to_id: int,
) -> Any:
    """Reassign a task to a different employee."""
    return await client.put(f"/tasks/employee/{task_id}/{assigned_to_id}")


async def create_project_from_template(
    client: PensionProClient,
    plan_id: int,
    template_id: int,
) -> dict[str, Any]:
    """Create a new project on a plan from a project template."""
    return await client.post("/projects", data={
        "PlanId": plan_id,
        "ProjectTemplateId": template_id,
        "HasBeenWarned": False,
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_projects.py -v`
Expected: All PASS.

- [ ] **Step 5: Register project tools on the MCP server**

Add to `src/pension_pro_mcp/server.py`:

```python
from pension_pro_mcp.tools.projects import (
    search_projects,
    get_project_details,
    complete_task,
    uncomplete_task,
    reassign_task,
    create_project_from_template,
)


@mcp.tool()
async def search_projects_tool(
    ctx: Context[ServerSession, AppContext],
    status: str | None = None,
    project_type: str | None = None,
    plan_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search and filter projects by status, type, or plan."""
    client = ctx.request_context.lifespan_context.client
    return await search_projects(client, status=status, project_type=project_type, plan_id=plan_id, limit=limit)


@mcp.tool()
async def get_project_details_tool(
    ctx: Context[ServerSession, AppContext],
    project_id: int,
) -> dict:
    """Get a project with its task groups, tasks, participants, and notes."""
    client = ctx.request_context.lifespan_context.client
    return await get_project_details(client, project_id=project_id)


@mcp.tool()
async def complete_task_tool(
    ctx: Context[ServerSession, AppContext],
    task_id: int,
) -> dict:
    """Mark a task as complete."""
    client = ctx.request_context.lifespan_context.client
    result = await complete_task(client, task_id=task_id)
    return {"success": True, "task_id": task_id, "result": result}


@mcp.tool()
async def uncomplete_task_tool(
    ctx: Context[ServerSession, AppContext],
    task_id: int,
) -> dict:
    """Undo task completion — revert a task to incomplete."""
    client = ctx.request_context.lifespan_context.client
    result = await uncomplete_task(client, task_id=task_id)
    return {"success": True, "task_id": task_id, "result": result}


@mcp.tool()
async def reassign_task_tool(
    ctx: Context[ServerSession, AppContext],
    task_id: int,
    assigned_to_id: int,
) -> dict:
    """Reassign a task to a different employee."""
    client = ctx.request_context.lifespan_context.client
    result = await reassign_task(client, task_id=task_id, assigned_to_id=assigned_to_id)
    return {"success": True, "task_id": task_id, "assigned_to_id": assigned_to_id, "result": result}


@mcp.tool()
async def create_project_from_template_tool(
    ctx: Context[ServerSession, AppContext],
    plan_id: int,
    template_id: int,
) -> dict:
    """Create a new project on a plan from a project template."""
    client = ctx.request_context.lifespan_context.client
    return await create_project_from_template(client, plan_id=plan_id, template_id=template_id)
```

- [ ] **Step 6: Commit**

```bash
git add src/pension_pro_mcp/tools/projects.py src/pension_pro_mcp/server.py tests/test_projects.py
git commit -m "feat: add project and task workflow tools"
```

---

### Task 6: Client & Contact Tools

**Files:**
- Create: `src/pension_pro_mcp/tools/clients.py`
- Create: `tests/test_clients.py`
- Modify: `src/pension_pro_mcp/server.py`

- [ ] **Step 1: Write failing tests**

`tests/test_clients.py`:
```python
"""Tests for client and contact tools."""

import pytest
import respx
import httpx

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.clients import search_clients, get_client_details, search_contacts


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> PensionProClient:
    monkeypatch.setenv("PENSION_PRO_API_KEY", "test-key")
    monkeypatch.setenv("PENSION_PRO_USERNAME", "test-user")
    return PensionProClient()


class TestSearchClients:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_clients(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/clients").mock(
            return_value=httpx.Response(200, json=[
                {"Id": 1, "CompanyNameId": "Acme Corp"},
            ])
        )
        result = await search_clients(client)
        assert len(result) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_filters_by_name(self, client: PensionProClient) -> None:
        route = respx.get("https://api.pensionpro.com/v2/clients").mock(
            return_value=httpx.Response(200, json=[])
        )
        await search_clients(client, name="Acme")
        request_url = str(route.calls[0].request.url)
        assert "contains(CompanyNameId" in request_url


class TestGetClientDetails:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_client_with_plans_and_contacts(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/clients/1").mock(
            return_value=httpx.Response(200, json={"Id": 1, "CompanyNameId": "Acme"})
        )
        respx.get("https://api.pensionpro.com/v2/clients/1/plans").mock(
            return_value=httpx.Response(200, json=[{"Id": 10, "Name": "401k"}])
        )
        respx.get("https://api.pensionpro.com/v2/clients/1/notes").mock(
            return_value=httpx.Response(200, json=[])
        )
        result = await get_client_details(client, client_id=1)
        assert result["client"]["CompanyNameId"] == "Acme"
        assert len(result["plans"]) == 1


class TestSearchContacts:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_contacts(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/contacts").mock(
            return_value=httpx.Response(200, json=[
                {"Id": 1, "FirstName": "Jane", "LastName": "Doe"},
            ])
        )
        result = await search_contacts(client)
        assert len(result) == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_filters_by_client_id(self, client: PensionProClient) -> None:
        route = respx.get("https://api.pensionpro.com/v2/contacts").mock(
            return_value=httpx.Response(200, json=[])
        )
        await search_contacts(client, client_id=5)
        request_url = str(route.calls[0].request.url)
        assert "ClientId" in request_url
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_clients.py -v`
Expected: FAIL — cannot import from `pension_pro_mcp.tools.clients`.

- [ ] **Step 3: Implement client and contact tools**

`src/pension_pro_mcp/tools/clients.py`:
```python
"""Client and contact lookup tools."""

from typing import Any

from pension_pro_mcp.client import PensionProClient


async def search_clients(
    client: PensionProClient,
    name: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search and filter clients."""
    filters: dict[str, str] = {}
    if name:
        filters["CompanyNameId__contains"] = name

    return await client.get_list("/clients", filters=filters, top=limit, max_total=limit)


async def get_client_details(
    client: PensionProClient,
    client_id: int,
) -> dict[str, Any]:
    """Get a client with their plans and notes."""
    client_data = await client.get(f"/clients/{client_id}")
    plans = await client.get(f"/clients/{client_id}/plans")
    notes = await client.get(f"/clients/{client_id}/notes")

    return {
        "client": client_data,
        "plans": plans if isinstance(plans, list) else [plans],
        "notes": notes if isinstance(notes, list) else [notes],
    }


async def search_contacts(
    client: PensionProClient,
    name: str | None = None,
    client_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search and filter contacts."""
    filters: dict[str, str] = {}
    if name:
        filters["LastName__contains"] = name
    if client_id:
        filters["ClientId"] = str(client_id)

    return await client.get_list("/contacts", filters=filters, top=limit, max_total=limit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_clients.py -v`
Expected: All PASS.

- [ ] **Step 5: Register client tools on the MCP server**

Add to `src/pension_pro_mcp/server.py`:

```python
from pension_pro_mcp.tools.clients import search_clients, get_client_details, search_contacts


@mcp.tool()
async def search_clients_tool(
    ctx: Context[ServerSession, AppContext],
    name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search and filter clients by company name."""
    client = ctx.request_context.lifespan_context.client
    return await search_clients(client, name=name, limit=limit)


@mcp.tool()
async def get_client_details_tool(
    ctx: Context[ServerSession, AppContext],
    client_id: int,
) -> dict:
    """Get a client with their plans and notes."""
    client = ctx.request_context.lifespan_context.client
    return await get_client_details(client, client_id=client_id)


@mcp.tool()
async def search_contacts_tool(
    ctx: Context[ServerSession, AppContext],
    name: str | None = None,
    client_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search and filter contacts by name or client."""
    client = ctx.request_context.lifespan_context.client
    return await search_contacts(client, name=name, client_id=client_id, limit=limit)
```

- [ ] **Step 6: Commit**

```bash
git add src/pension_pro_mcp/tools/clients.py src/pension_pro_mcp/server.py tests/test_clients.py
git commit -m "feat: add client and contact lookup tools"
```

---

### Task 7: To-Do Management Tools

**Files:**
- Create: `src/pension_pro_mcp/tools/todos.py`
- Create: `tests/test_todos.py`
- Modify: `src/pension_pro_mcp/server.py`

- [ ] **Step 1: Write failing tests**

`tests/test_todos.py`:
```python
"""Tests for to-do management tools."""

import pytest
import respx
import httpx

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.todos import search_todos, get_todo, create_todo, update_todo


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> PensionProClient:
    monkeypatch.setenv("PENSION_PRO_API_KEY", "test-key")
    monkeypatch.setenv("PENSION_PRO_USERNAME", "test-user")
    return PensionProClient()


class TestSearchTodos:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_todos(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/todos").mock(
            return_value=httpx.Response(200, json=[
                {"Id": 1, "ToDoName": "Review filing"},
            ])
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
            return_value=httpx.Response(200, json={"Id": 1, "ToDoName": "Review"})
        )
        respx.get("https://api.pensionpro.com/v2/todos/1/todocomments").mock(
            return_value=httpx.Response(200, json=[{"Id": 10, "CommentText": "Done"}])
        )
        result = await get_todo(client, todo_id=1)
        assert result["todo"]["ToDoName"] == "Review"
        assert len(result["comments"]) == 1


class TestCreateTodo:
    @respx.mock
    @pytest.mark.asyncio
    async def test_creates_todo_with_plan_link(self, client: PensionProClient) -> None:
        route = respx.post("https://api.pensionpro.com/v2/todos").mock(
            return_value=httpx.Response(200, json={"Id": 50, "ToDoName": "New task"})
        )
        result = await create_todo(
            client,
            subject="New task",
            plan_id=5,
        )
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
        # First GET the current todo to get its data
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_todos.py -v`
Expected: FAIL — cannot import from `pension_pro_mcp.tools.todos`.

- [ ] **Step 3: Implement to-do tools**

`src/pension_pro_mcp/tools/todos.py`:
```python
"""To-do management tools."""

from typing import Any

from pension_pro_mcp.client import PensionProClient

# Entity type IDs for ToDoLink
ENTITY_TYPE_PLAN = 1
ENTITY_TYPE_PROJECT = 4
ENTITY_TYPE_CONTACT = 7


async def search_todos(
    client: PensionProClient,
    status: str | None = None,
    priority: str | None = None,
    plan_id: int | None = None,
    project_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search and filter to-dos."""
    filters: dict[str, str] = {}
    if status:
        filters["ToDoStatus.DisplayName"] = status
    if priority:
        filters["Priority.DisplayName"] = priority

    if plan_id:
        endpoint = f"/plans/{plan_id}/todos"
    elif project_id:
        endpoint = f"/projects/{project_id}/todos"
    else:
        endpoint = "/todos"

    return await client.get_list(endpoint, filters=filters, top=limit, max_total=limit)


async def get_todo(
    client: PensionProClient,
    todo_id: int,
) -> dict[str, Any]:
    """Get a to-do with its comments."""
    todo = await client.get(f"/todos/{todo_id}")
    comments = await client.get(f"/todos/{todo_id}/todocomments")

    return {
        "todo": todo,
        "comments": comments if isinstance(comments, list) else [comments],
    }


async def create_todo(
    client: PensionProClient,
    subject: str,
    description: str | None = None,
    priority_id: int | None = None,
    due_date: str | None = None,
    status_id: int | None = None,
    assigned_to_contact_id: int | None = None,
    plan_id: int | None = None,
    project_id: int | None = None,
    contact_id: int | None = None,
) -> dict[str, Any]:
    """Create a new to-do, optionally linked to a plan, project, or contact."""
    data: dict[str, Any] = {
        "ToDoName": subject,
        "HasBeenWarned": False,
    }

    if description:
        data["Description"] = description
    if priority_id:
        data["PriorityId"] = priority_id
    if due_date:
        data["DueOn"] = due_date
    if status_id:
        data["ToDoStatusId"] = status_id
    if assigned_to_contact_id:
        data["AssignedToContactId"] = assigned_to_contact_id

    # Build ToDoLink if an entity is specified
    if plan_id:
        data["ToDoLink"] = {"EntityId": plan_id, "EntityTypeId": ENTITY_TYPE_PLAN, "HasBeenWarned": False}
    elif project_id:
        data["ToDoLink"] = {"EntityId": project_id, "EntityTypeId": ENTITY_TYPE_PROJECT, "HasBeenWarned": False}
    elif contact_id:
        data["ToDoLink"] = {"EntityId": contact_id, "EntityTypeId": ENTITY_TYPE_CONTACT, "HasBeenWarned": False}

    return await client.post("/todos", data=data)


async def update_todo(
    client: PensionProClient,
    todo_id: int,
    subject: str | None = None,
    description: str | None = None,
    status_id: int | None = None,
    priority_id: int | None = None,
    due_date: str | None = None,
) -> dict[str, Any]:
    """Update an existing to-do. Fetches current state first, then applies changes."""
    current = await client.get(f"/todos/{todo_id}")

    update_data: dict[str, Any] = {
        "Id": current["Id"],
        "DataKey": current.get("DataKey", ""),
        "ToDoName": subject if subject is not None else current.get("ToDoName", ""),
        "Description": description if description is not None else current.get("Description", ""),
        "ToDoStatusId": status_id if status_id is not None else current.get("ToDoStatusId", 0),
        "PriorityId": priority_id if priority_id is not None else current.get("PriorityId", 0),
        "DueOn": due_date if due_date is not None else current.get("DueOn"),
        "AssignedToContactId": current.get("AssignedToContactId", 0),
        "AssignedToTeamId": current.get("AssignedToTeamId", 0),
        "CompletedOn": current.get("CompletedOn"),
        "StartedOn": current.get("StartedOn"),
        "PercentageCompleted": current.get("PercentageCompleted", 0),
        "HasBeenWarned": current.get("HasBeenWarned", False),
        "IsDeactivated": current.get("IsDeactivated", False),
    }

    return await client.put(f"/todos/{todo_id}", data=update_data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_todos.py -v`
Expected: All PASS.

- [ ] **Step 5: Register to-do tools on the MCP server**

Add to `src/pension_pro_mcp/server.py`:

```python
from pension_pro_mcp.tools.todos import search_todos, get_todo, create_todo, update_todo


@mcp.tool()
async def search_todos_tool(
    ctx: Context[ServerSession, AppContext],
    status: str | None = None,
    priority: str | None = None,
    plan_id: int | None = None,
    project_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search and filter to-dos by status, priority, plan, or project."""
    client = ctx.request_context.lifespan_context.client
    return await search_todos(client, status=status, priority=priority, plan_id=plan_id, project_id=project_id, limit=limit)


@mcp.tool()
async def get_todo_tool(
    ctx: Context[ServerSession, AppContext],
    todo_id: int,
) -> dict:
    """Get a to-do with its comments."""
    client = ctx.request_context.lifespan_context.client
    return await get_todo(client, todo_id=todo_id)


@mcp.tool()
async def create_todo_tool(
    ctx: Context[ServerSession, AppContext],
    subject: str,
    description: str | None = None,
    priority_id: int | None = None,
    due_date: str | None = None,
    status_id: int | None = None,
    assigned_to_contact_id: int | None = None,
    plan_id: int | None = None,
    project_id: int | None = None,
    contact_id: int | None = None,
) -> dict:
    """Create a new to-do, optionally linked to a plan, project, or contact."""
    client = ctx.request_context.lifespan_context.client
    return await create_todo(
        client, subject=subject, description=description, priority_id=priority_id,
        due_date=due_date, status_id=status_id, assigned_to_contact_id=assigned_to_contact_id,
        plan_id=plan_id, project_id=project_id, contact_id=contact_id,
    )


@mcp.tool()
async def update_todo_tool(
    ctx: Context[ServerSession, AppContext],
    todo_id: int,
    subject: str | None = None,
    description: str | None = None,
    status_id: int | None = None,
    priority_id: int | None = None,
    due_date: str | None = None,
) -> dict:
    """Update an existing to-do's subject, description, status, priority, or due date."""
    client = ctx.request_context.lifespan_context.client
    return await update_todo(client, todo_id=todo_id, subject=subject, description=description, status_id=status_id, priority_id=priority_id, due_date=due_date)
```

- [ ] **Step 6: Commit**

```bash
git add src/pension_pro_mcp/tools/todos.py src/pension_pro_mcp/server.py tests/test_todos.py
git commit -m "feat: add to-do management tools (search, get, create, update)"
```

---

### Task 8: Notes Tools

**Files:**
- Create: `src/pension_pro_mcp/tools/notes.py`
- Create: `tests/test_notes.py`
- Modify: `src/pension_pro_mcp/server.py`

- [ ] **Step 1: Write failing tests**

`tests/test_notes.py`:
```python
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
        route = respx.post("https://api.pensionpro.com/v2/notes").mock(
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

    def test_raises_without_entity(self, client: PensionProClient) -> None:
        with pytest.raises(ValueError, match="At least one entity ID"):
            import asyncio
            asyncio.run(add_note(client, text="Orphan note"))

    @respx.mock
    @pytest.mark.asyncio
    async def test_adds_note_with_category(self, client: PensionProClient) -> None:
        route = respx.post("https://api.pensionpro.com/v2/notes").mock(
            return_value=httpx.Response(200, json={"Id": 4})
        )
        result = await add_note(client, text="Categorized", plan_id=1, category_id=3)
        assert result["Id"] == 4


class TestGetNotes:
    @respx.mock
    @pytest.mark.asyncio
    async def test_gets_notes_for_plan(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/plans/5/notes").mock(
            return_value=httpx.Response(200, json=[
                {"Id": 1, "NoteText": "Plan note"},
            ])
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

    def test_raises_without_entity(self, client: PensionProClient) -> None:
        with pytest.raises(ValueError, match="At least one entity ID"):
            import asyncio
            asyncio.run(get_notes(client))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_notes.py -v`
Expected: FAIL — cannot import from `pension_pro_mcp.tools.notes`.

- [ ] **Step 3: Implement notes tools**

`src/pension_pro_mcp/tools/notes.py`:
```python
"""Notes tools."""

from typing import Any

from pension_pro_mcp.client import PensionProClient


async def add_note(
    client: PensionProClient,
    text: str,
    plan_id: int | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
    contact_id: int | None = None,
    category_id: int | None = None,
) -> dict[str, Any]:
    """Add a note to a plan, project, task, or contact."""
    if not any([plan_id, project_id, task_id, contact_id]):
        raise ValueError("At least one entity ID (plan_id, project_id, task_id, contact_id) must be provided")

    data: dict[str, Any] = {
        "NoteText": text,
        "HasBeenWarned": False,
        "Archived": False,
        "IsImportant": False,
    }

    if plan_id:
        data["PlanId"] = plan_id
    if project_id:
        data["ProjectId"] = project_id
    if task_id:
        data["TaskId"] = task_id
    if contact_id:
        data["ContactId"] = contact_id
    if category_id:
        data["NoteCategoryId"] = category_id

    return await client.post("/notes", data=data)


async def get_notes(
    client: PensionProClient,
    plan_id: int | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
    contact_id: int | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Get notes for an entity (plan, project, task, or contact)."""
    if plan_id:
        endpoint = f"/plans/{plan_id}/notes"
    elif project_id:
        endpoint = f"/projects/{project_id}/notes"
    elif task_id:
        endpoint = f"/tasks/{task_id}/notes"
    elif contact_id:
        endpoint = f"/contacts/{contact_id}/notes"
    else:
        raise ValueError("At least one entity ID (plan_id, project_id, task_id, contact_id) must be provided")

    return await client.get_list(endpoint, top=limit, max_total=limit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_notes.py -v`
Expected: All PASS.

- [ ] **Step 5: Register notes tools on the MCP server**

Add to `src/pension_pro_mcp/server.py`:

```python
from pension_pro_mcp.tools.notes import add_note, get_notes


@mcp.tool()
async def add_note_tool(
    ctx: Context[ServerSession, AppContext],
    text: str,
    plan_id: int | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
    contact_id: int | None = None,
    category_id: int | None = None,
) -> dict:
    """Add a note to a plan, project, task, or contact. At least one entity ID must be provided."""
    client = ctx.request_context.lifespan_context.client
    return await add_note(client, text=text, plan_id=plan_id, project_id=project_id, task_id=task_id, contact_id=contact_id, category_id=category_id)


@mcp.tool()
async def get_notes_tool(
    ctx: Context[ServerSession, AppContext],
    plan_id: int | None = None,
    project_id: int | None = None,
    task_id: int | None = None,
    contact_id: int | None = None,
    limit: int = 25,
) -> list[dict]:
    """Get notes for an entity (plan, project, task, or contact). At least one entity ID must be provided."""
    client = ctx.request_context.lifespan_context.client
    return await get_notes(client, plan_id=plan_id, project_id=project_id, task_id=task_id, contact_id=contact_id, limit=limit)
```

- [ ] **Step 6: Commit**

```bash
git add src/pension_pro_mcp/tools/notes.py src/pension_pro_mcp/server.py tests/test_notes.py
git commit -m "feat: add notes tools (add_note, get_notes)"
```

---

### Task 9: README and GitHub Repo Setup

**Files:**
- Create: `README.md`
- Create: `.gitignore`

- [ ] **Step 1: Create .gitignore**

`.gitignore`:
```
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/
*.egg
.pytest_cache/
.venv/
venv/
env/
.env
```

- [ ] **Step 2: Create README.md**

`README.md`:
```markdown
# PensionPro MCP Server

A local, open-source [MCP](https://modelcontextprotocol.io/) server that provides AI assistants with tools to interact with the [PensionPro](https://pensionpro.com/) REST API.

## Features

- **Plan Lookup & Search** — Search plans by name, status, type, or client. Get comprehensive plan details with contacts, cycles, and fee schedules.
- **Project & Task Workflow** — Search projects, view task details, complete/uncomplete tasks, reassign tasks, and create projects from templates.
- **Client & Contact Lookup** — Search clients and contacts, view client details with associated plans.
- **To-Do Management** — Search, create, and update to-dos linked to plans, projects, or contacts.
- **Notes** — Add and retrieve notes on plans, projects, tasks, and contacts.

## Prerequisites

- Python 3.12+
- A PensionPro API key and username

## Installation

```bash
pip install git+https://github.com/douglaslinsmeyer/pension-pro-mcp.git
```

Or run directly with [uvx](https://docs.astral.sh/uv/):

```bash
uvx --from git+https://github.com/douglaslinsmeyer/pension-pro-mcp.git pension-pro-mcp
```

## Configuration

Set the following environment variables:

```bash
export PENSION_PRO_API_KEY=your_api_key
export PENSION_PRO_USERNAME=your_username
```

### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pension-pro": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/douglaslinsmeyer/pension-pro-mcp.git", "pension-pro-mcp"],
      "env": {
        "PENSION_PRO_API_KEY": "your_api_key",
        "PENSION_PRO_USERNAME": "your_username"
      }
    }
  }
}
```

### Claude Code

Add to your `.claude/settings.json`:

```json
{
  "mcpServers": {
    "pension-pro": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/douglaslinsmeyer/pension-pro-mcp.git", "pension-pro-mcp"],
      "env": {
        "PENSION_PRO_API_KEY": "your_api_key",
        "PENSION_PRO_USERNAME": "your_username"
      }
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `search_plans_tool` | Search and filter plans by name, status, type, or client |
| `get_plan_details_tool` | Get plan with contacts, cycles, services, investments, fees |
| `get_plan_projects_tool` | Get projects for a plan with task completion summaries |
| `search_projects_tool` | Search and filter projects by status, type, or plan |
| `get_project_details_tool` | Get project with task groups, tasks, participants, notes |
| `complete_task_tool` | Mark a task as complete |
| `uncomplete_task_tool` | Revert a task to incomplete |
| `reassign_task_tool` | Reassign a task to a different employee |
| `create_project_from_template_tool` | Create a new project from a template |
| `search_clients_tool` | Search and filter clients by company name |
| `get_client_details_tool` | Get client with plans and notes |
| `search_contacts_tool` | Search and filter contacts by name or client |
| `search_todos_tool` | Search and filter to-dos |
| `get_todo_tool` | Get a to-do with its comments |
| `create_todo_tool` | Create a new to-do linked to an entity |
| `update_todo_tool` | Update a to-do's details |
| `add_note_tool` | Add a note to a plan, project, task, or contact |
| `get_notes_tool` | Get notes for an entity |

## Development

```bash
git clone https://github.com/douglaslinsmeyer/pension-pro-mcp.git
cd pension-pro-mcp
pip install -e ".[dev]"
pytest
```

## License

MIT
```

- [ ] **Step 3: Create the GitHub repo**

Run: `gh repo create douglaslinsmeyer/pension-pro-mcp --public --description "MCP server for the PensionPro API" --source . --push`

- [ ] **Step 4: Commit and push**

```bash
git add .gitignore README.md
git commit -m "docs: add README and .gitignore"
git push -u origin master
```

---

### Task 10: Run Full Test Suite and Verify

- [ ] **Step 1: Run the complete test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 2: Verify the server can start**

Run: `PENSION_PRO_API_KEY=test PENSION_PRO_USERNAME=test timeout 2 python -m pension_pro_mcp.server 2>&1 || true`
Expected: Server starts (may timeout after 2s waiting for stdio — that's fine).

- [ ] **Step 3: Verify tool count**

Run: `python -c "from pension_pro_mcp.server import mcp; print(f'Registered {len(mcp._tool_manager._tools)} tools')" 2>/dev/null || python -c "from pension_pro_mcp.server import mcp; print('Server loaded successfully')"`
Expected: 18 tools registered (or at minimum, server loads without import errors).
