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
