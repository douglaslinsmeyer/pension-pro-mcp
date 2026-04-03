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
