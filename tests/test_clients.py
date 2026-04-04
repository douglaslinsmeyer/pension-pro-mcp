"""Tests for client and contact tools."""

import pytest
import respx
import httpx

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.clients import search_clients, get_client_details, search_contacts


class TestSearchClients:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_clients(self, client: PensionProClient) -> None:
        respx.get("https://api.pensionpro.com/v2/clients").mock(
            return_value=httpx.Response(200, json=[{"Id": 1, "CompanyNameId": "Acme Corp"}])
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
    async def test_returns_client_with_plans_and_notes(self, client: PensionProClient) -> None:
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
            return_value=httpx.Response(200, json=[{"Id": 1, "FirstName": "Jane", "LastName": "Doe"}])
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
