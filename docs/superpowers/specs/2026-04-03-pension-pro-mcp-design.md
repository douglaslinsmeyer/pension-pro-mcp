# PensionPro MCP Server — Design Spec

## Overview

A local, open-source MCP (Model Context Protocol) server that wraps the PensionPro REST API (v2) into domain-oriented tools for AI assistants. It enables pension administrators to look up plan/project/client data and manage workflows through natural language conversations.

- **Repository:** `douglaslinsmeyer/pension-pro-mcp`
- **Language:** Python
- **License:** MIT
- **Target users:** Internal pension administration team

## PensionPro API Summary

- **Base URL:** `https://api.pensionpro.com`
- **Version:** v2
- **Auth:** Single header `apikey-username` with value `{API_KEY}|{USERNAME}`
- **Query support:** OData v4 (`$filter`, `$expand`, `$orderby`, `$top`, `$skip`)
- **Max results per request:** 1000
- **Endpoint count:** 574 across 81 resource groups
- **Swagger spec:** `https://api.pensionpro.com/swagger/PensionPro.API%20v2/swagger.json`

## Architecture

### Project Structure

```
pension-pro-mcp/
├── src/
│   └── pension_pro_mcp/
│       ├── __init__.py
│       ├── server.py          # MCP server setup + tool registration
│       ├── client.py          # PensionPro API client (auth, OData, pagination)
│       └── tools/
│           ├── __init__.py
│           ├── plans.py       # Plan lookup & search tools
│           ├── projects.py    # Project & task workflow tools
│           ├── clients.py     # Client & contact tools
│           ├── todos.py       # To-do management tools
│           └── notes.py       # Notes tools
├── tests/
│   ├── conftest.py            # Shared fixtures (mock API client, respx routes)
│   ├── test_client.py         # API client tests
│   ├── test_plans.py
│   ├── test_projects.py
│   ├── test_clients.py
│   ├── test_todos.py
│   └── test_notes.py
├── pyproject.toml
├── README.md
└── LICENSE
```

### Key Components

**`server.py`** — MCP server entry point. Creates the `Server` instance, registers all tools from the tools modules, and runs the stdio transport. Provides a `main()` function as the CLI entry point.

**`client.py`** — Async HTTP client wrapping the PensionPro API. Responsibilities:
- Reads `PENSION_PRO_API_KEY` and `PENSION_PRO_USERNAME` from environment variables
- Constructs the `apikey-username` header
- Provides typed methods for GET, POST, PUT, DELETE
- Builds OData query strings (`$filter`, `$expand`, `$orderby`, `$top`, `$skip`)
- Handles pagination automatically for list endpoints (follows `$skip`/`$top` to fetch all pages up to a configurable limit)
- Surfaces API errors as structured exceptions with status code and message
- Uses `httpx.AsyncClient` with connection pooling

**`tools/*.py`** — Each module registers MCP tools for a domain. Tools call the API client and shape responses into useful summaries. Tools are domain-oriented, not 1:1 with API endpoints — a single tool may aggregate multiple API calls.

## MCP Tools

### Plan Lookup & Search (3 tools)

#### `search_plans`
Search and filter plans. Returns a summary list.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | no | Filter by plan name (partial match) |
| `status` | string | no | Filter by plan status |
| `plan_type` | string | no | Filter by plan type |
| `client_name` | string | no | Filter by client company name |
| `limit` | int | no | Max results (default 50) |

Returns: List of `{ id, name, status, planType, clientName, internalPlanId }`.

#### `get_plan_details`
Get comprehensive details for a single plan.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `plan_id` | int | yes | The plan ID |

Aggregates: plan record + contacts/roles + plan cycles + services provided + investment providers + fee schedules.

Returns: Full plan object with nested related data.

#### `get_plan_projects`
Get all projects for a plan with status summaries.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `plan_id` | int | yes | The plan ID |
| `status` | string | no | Filter by project status |

Returns: List of projects with `{ id, name, status, type, taskSummary: { total, completed, pending } }`.

### Project & Task Workflow (6 tools)

#### `search_projects`
Search and filter projects.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `status` | string | no | Filter by project status |
| `project_type` | string | no | Filter by project type |
| `plan_id` | int | no | Filter by plan |
| `limit` | int | no | Max results (default 50) |

Returns: List of `{ id, name, status, type, planName, planId }`.

#### `get_project_details`
Get a project with full task and participant details.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | int | yes | The project ID |

Aggregates: project record + task groups + tasks (with state) + participants + notes.

Returns: Full project object with nested task groups/tasks, participants, and recent notes.

#### `complete_task`
Mark a task as complete.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | int | yes | The task ID |

Calls: `PUT /v2/tasks/{taskId}/completetask`.

#### `uncomplete_task`
Undo task completion.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | int | yes | The task ID |

Calls: `PUT /v2/tasks/{taskId}/uncompletetask`.

#### `reassign_task`
Reassign a task to a different employee.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | int | yes | The task ID |
| `assigned_to_id` | int | yes | The employee ID to assign to |

Calls: `PUT /v2/tasks/employee/{taskId}/{assignedToId}`.

#### `create_project_from_template`
Create a new project on a plan from a project template.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `plan_id` | int | yes | The plan to create the project on |
| `template_id` | int | yes | The project template ID |

Calls: `POST /v2/projects` with template reference.

### Client & Contact Lookup (3 tools)

#### `search_clients`
Search and filter clients.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | no | Filter by company name (partial match) |
| `limit` | int | no | Max results (default 50) |

Returns: List of `{ id, companyName, location, isDeactivated }`.

#### `get_client_details`
Get a client with their plans, contacts, and locations.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `client_id` | int | yes | The client ID |

Aggregates: client record + plans + contacts + locations.

Returns: Full client object with nested plans, contacts, and locations.

#### `search_contacts`
Search and filter contacts.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | no | Filter by contact name (partial match) |
| `client_id` | int | no | Filter by client |
| `limit` | int | no | Max results (default 50) |

Returns: List of `{ id, firstName, lastName, email, clientName }`.

### To-Do Management (4 tools)

#### `search_todos`
Search and filter to-dos.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `status` | string | no | Filter by to-do status |
| `priority` | string | no | Filter by priority |
| `plan_id` | int | no | Filter to-dos for a specific plan |
| `project_id` | int | no | Filter to-dos for a specific project |
| `limit` | int | no | Max results (default 50) |

Returns: List of to-do summaries.

#### `get_todo`
Get a to-do with its comments and links.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `todo_id` | int | yes | The to-do ID |

Aggregates: to-do record + comments + links.

#### `create_todo`
Create a new to-do.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `subject` | string | yes | To-do subject |
| `description` | string | no | To-do description |
| `priority` | string | no | Priority level |
| `due_date` | string | no | Due date (ISO format) |
| `plan_id` | int | no | Link to a plan |
| `project_id` | int | no | Link to a project |
| `contact_id` | int | no | Link to a contact |

#### `update_todo`
Update an existing to-do.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `todo_id` | int | yes | The to-do ID |
| `status` | string | no | New status |
| `priority` | string | no | New priority |
| `subject` | string | no | New subject |
| `description` | string | no | New description |
| `due_date` | string | no | New due date |

### Notes (2 tools)

#### `add_note`
Add a note to an entity.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `text` | string | yes | Note text |
| `plan_id` | int | no | Attach to plan |
| `project_id` | int | no | Attach to project |
| `task_id` | int | no | Attach to task |
| `contact_id` | int | no | Attach to contact |
| `category` | string | no | Note category |

At least one entity ID must be provided.

#### `get_notes`
Get notes for an entity.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `plan_id` | int | no | Get notes for plan |
| `project_id` | int | no | Get notes for project |
| `task_id` | int | no | Get notes for task |
| `contact_id` | int | no | Get notes for contact |
| `limit` | int | no | Max results (default 25) |

At least one entity ID must be provided.

## API Client Design

### Authentication

```python
# Environment variables
PENSION_PRO_API_KEY=your_api_key
PENSION_PRO_USERNAME=your_username

# Sent as header on every request
headers = {
    "apikey-username": f"{api_key}|{username}"
}
```

### OData Query Builder

The client provides a query builder that translates tool parameters into OData query strings:

- **`$filter`**: Translates field/value pairs into OData filter expressions (e.g., `Name eq 'Acme'`, `contains(Name, 'Acme')`)
- **`$expand`**: Includes related entities in the response
- **`$orderby`**: Sort results
- **`$top` / `$skip`**: Pagination (server max 1000 per page)

### Pagination

For list endpoints, the client automatically paginates by incrementing `$skip` until fewer results than `$top` are returned, up to a configurable maximum total (default 5000). Tools can set their own limits via the `limit` parameter.

### Error Handling

API errors are caught and returned as structured MCP tool errors with:
- HTTP status code
- Error message from the API response body
- The endpoint that failed

## Testing Strategy

- **Framework:** `pytest` with `pytest-asyncio`
- **HTTP mocking:** `respx` (mocks at the `httpx` transport layer — real client code runs, only HTTP is faked)
- **BDD-style:** Descriptive test names following Given/When/Then pattern
- **Coverage areas:**
  - API client: auth header construction, OData query building, pagination logic, error handling
  - Each tool: parameter validation, correct API calls composed, response shaping
  - OData builder: filter expression generation, edge cases

## Packaging & Distribution

### `pyproject.toml`

- Build system: `hatchling`
- Dependencies: `mcp`, `httpx`
- Dev dependencies: `pytest`, `pytest-asyncio`, `respx`
- Entry point: `pension-pro-mcp = "pension_pro_mcp.server:main"`

### Installation & Usage

```bash
# Install from GitHub
pip install git+https://github.com/douglaslinsmeyer/pension-pro-mcp.git

# Or run directly with uvx
uvx --from git+https://github.com/douglaslinsmeyer/pension-pro-mcp.git pension-pro-mcp
```

### MCP Client Configuration

**Claude Desktop (`claude_desktop_config.json`):**
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

**Claude Code (`.claude/settings.json`):**
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
