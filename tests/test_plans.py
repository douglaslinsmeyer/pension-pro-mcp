"""Tests for plan tools."""

import pytest
import respx
import httpx

from pension_pro_mcp.client import PensionProClient
from pension_pro_mcp.tools.plans import search_plans, get_plan_details, get_plan_projects


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
        assert "contains(SearchText" in request_url


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
