# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Python MCP server wrapping the PensionPro REST API v2. Enables AI assistants to interact with pension administration workflows (plans, projects, tasks, clients, to-dos, notes, worktrays) via the Model Context Protocol.

## Commands

```bash
# Install for development
uv pip install -e ".[dev]"

# Run all tests
pytest

# Run a single test file
pytest tests/test_plans.py

# Run a single test class or method
pytest tests/test_plans.py::TestSearchPlans::test_applies_name_filter

# Run the MCP server locally (requires PENSION_PRO_API_KEY and PENSION_PRO_USERNAME env vars)
uvx pension-pro-mcp

# Refresh bundled help articles from PensionPro knowledge base
python scripts/scrape_docs.py
```

## Architecture

**Three-layer design:**

1. **`client.py`** — Async httpx client with OData v4 query building (`build_odata_params`), automatic pagination (`get_list`), and structured error handling (`PensionProError`). All API calls go through this client.

2. **`pipeline.py`** — Ordered chain of response transforms applied to tool outputs. Default pipeline: unwrap paginated `{"Values": [...], "TotalCount": N}` responses → strip null/empty-string keys. Tools use `pipeline.wrap(fn)` decorator or call `pipeline.apply(data)`.

3. **`tools/`** — One module per domain (plans, projects, clients, todos, notes, worktrays, swagger, help). Each module exports async functions that take a `PensionProClient` and typed parameters, returning dicts/lists. These are registered as MCP tools in `server.py`.

**`server.py`** ties it all together: creates `AppContext` (holds client + cached swagger spec) via async lifespan, registers all 26 tools with `FastMCP`, and handles swagger spec caching (24-hour TTL in platform-appropriate cache dir).

## Key Patterns

- **OData filter convention**: Use `field__contains` key suffix for `contains()` filters; bare keys become `eq` comparisons. Values `"true"/"false"/"null"` and digit-only strings are unquoted.
- **Fetch-then-update for PUT operations**: Always GET the current resource, merge changes, then PUT the full object back. This preserves server-managed fields.
- **Aggregating tools**: Single tool functions often make multiple API calls to assemble rich responses (e.g., `get_plan_details` fetches plan + contacts + cycles + fees in parallel).
- **Pipeline wrapping**: Tool functions that return API data are wrapped with `pipeline.wrap()` so transforms apply automatically.

## Testing

- **Framework**: pytest + pytest-asyncio + respx (HTTP response mocking)
- **Shared fixture**: `conftest.py` provides a `client` fixture that monkeypatches env vars and returns a `PensionProClient`
- **Pattern**: Use `@respx.mock` decorator, mock full URLs (`https://api.pensionpro.com/v2/...`), call the tool function directly with the client fixture, assert on results and on sent request URLs/bodies via `route.calls`
- **Test organization**: One test file per tool module, test classes per tool function

## PensionPro Domain Model

```
Client → Plan → Contacts, Cycles, Services, Investments, Fees
              → Projects → Task Groups → Tasks
              → Distributions (special project type)
Worktrays (shared task queues assigned to employees)
To-Dos (independent items, linkable to plans/projects/contacts)
Notes (attachable to plans/projects/tasks/contacts)
```
