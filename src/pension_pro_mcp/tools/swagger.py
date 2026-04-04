"""Tools for searching and exploring the PensionPro API swagger spec."""

from typing import Any

SWAGGER_URL = "https://api.pensionpro.com/swagger/PensionPro.API%20v2/swagger.json"


def search_paths(spec: dict[str, Any], keyword: str) -> list[dict[str, Any]]:
    """Search API endpoints by keyword. Returns matching paths with their HTTP methods."""
    keyword = keyword.lower()
    results = []
    for path, methods in sorted(spec["paths"].items()):
        if keyword in path.lower():
            results.append({
                "path": path,
                "methods": [
                    {"method": method.upper(), "summary": detail.get("summary", "")}
                    for method, detail in methods.items()
                    if method in ("get", "post", "put", "delete", "patch", "head")
                ],
            })
    return results


def get_endpoint(spec: dict[str, Any], path: str) -> dict[str, Any]:
    """Get full details for a specific API endpoint including parameters and response schemas."""
    for p, detail in spec["paths"].items():
        if p == path or p.endswith(path):
            return {"path": p, "details": detail}
    return {"error": f"Endpoint not found: {path}"}


def search_schemas(spec: dict[str, Any], keyword: str) -> list[dict[str, Any]]:
    """Search API data models/schemas by keyword. Returns matching schema names and their fields."""
    keyword = keyword.lower()
    schemas = spec.get("components", {}).get("schemas", {})
    results = []
    for name in sorted(schemas):
        if keyword in name.lower():
            schema = schemas[name]
            props = list(schema.get("properties", {}).keys())
            results.append({
                "name": name,
                "description": schema.get("description", ""),
                "fields": props,
            })
    return results


def get_schema(spec: dict[str, Any], name: str) -> dict[str, Any]:
    """Get the full definition of a specific API data model/schema."""
    schemas = spec.get("components", {}).get("schemas", {})
    for schema_name, schema_def in schemas.items():
        if schema_name.lower() == name.lower():
            return {"name": schema_name, "definition": schema_def}
    return {"error": f"Schema not found: {name}"}
