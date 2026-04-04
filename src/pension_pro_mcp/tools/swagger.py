"""Tools for searching and exploring the PensionPro API swagger spec."""

from typing import Any

SWAGGER_URL = "https://api.pensionpro.com/swagger/PensionPro.API%20v2/swagger.json"


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    """Resolve a $ref pointer like '#/components/schemas/Foo' to its definition."""
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        node = node.get(part, {})
    return node


def _format_type(prop: dict[str, Any], spec: dict[str, Any]) -> str:
    """Format a property's type into a compact string."""
    if "$ref" in prop:
        ref_name = prop["$ref"].rsplit("/", 1)[-1]
        return ref_name

    prop_type = prop.get("type", "any")

    if prop_type == "array":
        items = prop.get("items", {})
        if "$ref" in items:
            item_type = items["$ref"].rsplit("/", 1)[-1]
        else:
            item_type = items.get("type", "any")
            fmt = items.get("format")
            if fmt:
                item_type = f"{item_type} ({fmt})"
        return f"array[{item_type}]"

    fmt = prop.get("format")
    if fmt:
        prop_type = f"{prop_type} ({fmt})"

    return prop_type


def _format_schema(name: str, schema_def: dict[str, Any], spec: dict[str, Any]) -> str:
    """Format a schema into a compact readable representation."""
    lines = [f"{name}:"]
    desc = schema_def.get("description", "")
    if desc:
        lines.append(f"  {desc}")

    required = set(schema_def.get("required", []))
    properties = schema_def.get("properties", {})

    for prop_name, prop_def in properties.items():
        type_str = _format_type(prop_def, spec)
        nullable = prop_def.get("nullable", False)
        is_required = prop_name in required

        annotations = []
        if is_required:
            annotations.append("required")
        if nullable:
            annotations.append("nullable")

        suffix = f" ({', '.join(annotations)})" if annotations else ""
        lines.append(f"  {prop_name}: {type_str}{suffix}")

    return "\n".join(lines)


def _format_endpoint(path: str, detail: dict[str, Any], spec: dict[str, Any]) -> str:
    """Format an endpoint into a compact readable representation."""
    lines = [f"Path: {path}", ""]

    for method, method_detail in detail.items():
        if method not in ("get", "post", "put", "delete", "patch"):
            continue

        lines.append(f"{method.upper()}: {method_detail.get('summary', '')}")

        params = method_detail.get("parameters", [])
        if params:
            lines.append("  Parameters:")
            for param in params:
                param_name = param.get("name", "")
                param_in = param.get("in", "")
                param_required = param.get("required", False)
                param_schema = param.get("schema", {})
                param_type = param_schema.get("type", "string")
                req = " (required)" if param_required else ""
                lines.append(f"    {param_name} [{param_in}]: {param_type}{req}")

        # Response schema
        responses = method_detail.get("responses", {})
        ok_response = responses.get("200", {})
        content = ok_response.get("content", {})
        json_content = content.get("application/json", {})
        resp_schema = json_content.get("schema", {})
        if resp_schema:
            if "$ref" in resp_schema:
                ref_name = resp_schema["$ref"].rsplit("/", 1)[-1]
                lines.append(f"  Returns: {ref_name}")
            elif resp_schema.get("type") == "array" and "$ref" in resp_schema.get("items", {}):
                ref_name = resp_schema["items"]["$ref"].rsplit("/", 1)[-1]
                lines.append(f"  Returns: array[{ref_name}]")

        lines.append("")

    return "\n".join(lines)


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


def get_endpoint(
    spec: dict[str, Any], path: str, raw: bool = False,
) -> dict[str, Any] | str:
    """Get details for a specific API endpoint."""
    for p, detail in spec["paths"].items():
        if p == path or p.endswith(path):
            if raw:
                return {"path": p, "details": detail}
            return _format_endpoint(p, detail, spec)
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


def get_schema(
    spec: dict[str, Any], name: str, raw: bool = False,
) -> dict[str, Any] | str:
    """Get the definition of a specific API data model/schema."""
    schemas = spec.get("components", {}).get("schemas", {})
    for schema_name, schema_def in schemas.items():
        if schema_name.lower() == name.lower():
            if raw:
                return {"name": schema_name, "definition": schema_def}
            return _format_schema(schema_name, schema_def, spec)
    return {"error": f"Schema not found: {name}"}
