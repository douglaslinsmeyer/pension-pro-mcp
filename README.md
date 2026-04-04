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

Install from [PyPI](https://pypi.org/project/pension-pro-mcp/):

```bash
pip install pension-pro-mcp
```

Or run directly with [uvx](https://docs.astral.sh/uv/) (no install required):

```bash
uvx pension-pro-mcp
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
      "args": ["pension-pro-mcp"],
      "env": {
        "PENSION_PRO_API_KEY": "your_api_key",
        "PENSION_PRO_USERNAME": "your_username"
      }
    }
  }
}
```

### Claude Code

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "pension-pro": {
      "command": "uvx",
      "args": ["pension-pro-mcp"],
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
| `search_plans` | Search and filter plans by name, status, type, or client |
| `get_plan_details` | Get plan with contacts, cycles, services, investments, fees |
| `get_plan_projects` | Get projects for a plan with task completion summaries |
| `search_projects` | Search and filter projects by status, type, or plan |
| `get_project_details` | Get project with task groups, tasks, participants, notes, and files |
| `get_task_details` | Get a single task with state, assignment, and notes |
| `complete_task` | Mark a task as complete |
| `uncomplete_task` | Revert a task to incomplete |
| `reassign_task` | Reassign a task to a different employee |
| `create_project_from_template` | Create a new project from a template |
| `search_clients` | Search and filter clients by company name |
| `get_client_details` | Get client with plans and notes |
| `search_contacts` | Search and filter contacts by name or client |
| `search_todos` | Search and filter to-dos |
| `get_todo` | Get a to-do with its comments |
| `create_todo` | Create a new to-do linked to an entity |
| `update_todo` | Update a to-do's details |
| `add_note` | Add a note to a plan, project, task, or contact |
| `get_notes` | Get notes for an entity |
| `search_api_paths` | Search PensionPro API endpoints by keyword |
| `get_api_endpoint` | Get full details for a specific API endpoint |
| `search_api_schemas` | Search API data models/schemas by keyword |
| `get_api_schema` | Get the full definition of an API data model |
| `search_help_articles` | Search PensionPro help center articles by keyword |
| `get_help_article` | Get the full content of a help article |
| `list_help_sections` | List available help sections with article counts |

## Development

```bash
git clone https://github.com/douglaslinsmeyer/pension-pro-mcp.git
cd pension-pro-mcp
pip install -e ".[dev]"
pytest
```

### Refreshing Help Articles

The bundled help articles can be refreshed from the PensionPro knowledge base:

```bash
python scripts/scrape_docs.py
```

## License

MIT
