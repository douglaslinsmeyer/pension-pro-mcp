#!/usr/bin/env python3
"""CLI tool for querying the PensionPro API swagger spec.

Usage:
    # List all paths matching a keyword
    python scripts/swagger.py paths distribution

    # Show details for a specific endpoint
    python scripts/swagger.py endpoint /v2/projects/{projectId}/distributionfiles

    # List all schemas matching a keyword
    python scripts/swagger.py schemas distribution

    # Show a specific schema
    python scripts/swagger.py schema DistributionFile
"""

import json
import sys
from pathlib import Path

SWAGGER_PATH = Path(__file__).parent.parent / "docs" / "swagger.json"


def load_spec() -> dict:
    with open(SWAGGER_PATH) as f:
        spec = json.load(f)
    # Only keep v2 endpoints — v1 is being deprecated
    spec["paths"] = {p: v for p, v in spec["paths"].items() if p.startswith("/v2/")}
    return spec


def cmd_paths(spec: dict, keyword: str) -> None:
    """List all paths containing the keyword."""
    keyword = keyword.lower()
    for path in sorted(spec["paths"]):
        if keyword in path.lower():
            methods = ", ".join(spec["paths"][path].keys())
            print(f"{path}  [{methods}]")


def cmd_endpoint(spec: dict, path: str) -> None:
    """Show full details for a specific endpoint."""
    # Normalize: strip base path if provided
    for p in spec["paths"]:
        if p == path or p.endswith(path):
            print(json.dumps(spec["paths"][p], indent=2))
            return
    print(f"Endpoint not found: {path}")
    sys.exit(1)


def cmd_schemas(spec: dict, keyword: str) -> None:
    """List all schemas containing the keyword."""
    keyword = keyword.lower()
    schemas = spec.get("components", {}).get("schemas", {})
    for name in sorted(schemas):
        if keyword in name.lower():
            desc = schemas[name].get("description", "")
            props = list(schemas[name].get("properties", {}).keys())
            print(f"{name}: {desc}")
            if props:
                print(f"  fields: {', '.join(props[:15])}")
                if len(props) > 15:
                    print(f"  ... and {len(props) - 15} more")
            print()


def cmd_schema(spec: dict, name: str) -> None:
    """Show a specific schema definition."""
    schemas = spec.get("components", {}).get("schemas", {})
    # Case-insensitive match
    for schema_name, schema_def in schemas.items():
        if schema_name.lower() == name.lower():
            print(json.dumps({schema_name: schema_def}, indent=2))
            return
    print(f"Schema not found: {name}")
    sys.exit(1)


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    spec = load_spec()
    command = sys.argv[1]
    arg = sys.argv[2]

    commands = {
        "paths": cmd_paths,
        "endpoint": cmd_endpoint,
        "schemas": cmd_schemas,
        "schema": cmd_schema,
    }

    if command not in commands:
        print(f"Unknown command: {command}")
        print(f"Available: {', '.join(commands)}")
        sys.exit(1)

    commands[command](spec, arg)


if __name__ == "__main__":
    main()
