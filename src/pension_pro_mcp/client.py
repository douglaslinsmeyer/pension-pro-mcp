"""PensionPro API client."""

import os
from typing import Any

import httpx


class PensionProError(Exception):
    """Raised when the PensionPro API returns an error."""

    def __init__(self, status_code: int, message: str, endpoint: str) -> None:
        self.status_code = status_code
        self.message = message
        self.endpoint = endpoint
        super().__init__(f"PensionPro API error {status_code} on {endpoint}: {message}")


class PensionProClient:
    """Async HTTP client for the PensionPro REST API v2."""

    BASE_URL = "https://api.pensionpro.com/v2"

    def __init__(self) -> None:
        api_key = os.environ.get("PENSION_PRO_API_KEY", "")
        username = os.environ.get("PENSION_PRO_USERNAME", "")
        if not api_key or not username:
            raise ValueError(
                "PENSION_PRO_API_KEY and PENSION_PRO_USERNAME environment variables are required"
            )
        self._http = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"ApiKey": api_key, "Username": username},
            timeout=30.0,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    async def _handle_response(self, response: httpx.Response, endpoint: str) -> Any:
        """Check response status and return parsed JSON."""
        if response.status_code >= 400:
            try:
                body = response.json()
                message = body.get("Message", str(body))
            except Exception:
                message = response.text or f"HTTP {response.status_code}"
            raise PensionProError(response.status_code, message, endpoint)
        return response.json()

    async def get(self, endpoint: str, params: dict[str, str] | None = None) -> Any:
        """Send a GET request."""
        response = await self._http.get(endpoint, params=params)
        return await self._handle_response(response, endpoint)

    async def post(self, endpoint: str, data: dict[str, Any] | None = None) -> Any:
        """Send a POST request with a JSON body."""
        response = await self._http.post(endpoint, json=data)
        return await self._handle_response(response, endpoint)

    async def put(self, endpoint: str, data: dict[str, Any] | None = None) -> Any:
        """Send a PUT request with an optional JSON body."""
        response = await self._http.put(endpoint, json=data)
        return await self._handle_response(response, endpoint)

    async def delete(self, endpoint: str) -> Any:
        """Send a DELETE request."""
        response = await self._http.delete(endpoint)
        return await self._handle_response(response, endpoint)

    def build_odata_params(
        self,
        filters: dict[str, str] | None = None,
        expand: list[str] | None = None,
        orderby: str | None = None,
        top: int | None = None,
        skip: int | None = None,
    ) -> dict[str, str]:
        """Build OData query parameters from structured inputs."""
        params: dict[str, str] = {}

        if filters:
            clauses: list[str] = []
            for key, value in filters.items():
                escaped = value.replace("'", "''")
                if key.endswith("__contains"):
                    field = key[: -len("__contains")]
                    clauses.append(f"contains({field}, '{escaped}')")
                elif key.endswith("__ge"):
                    field = key[: -len("__ge")]
                    clauses.append(f"{field} ge '{escaped}'")
                elif key.endswith("__le"):
                    field = key[: -len("__le")]
                    clauses.append(f"{field} le '{escaped}'")
                elif value in ("true", "false", "null"):
                    clauses.append(f"{key} eq {value}")
                elif value.isdigit():
                    clauses.append(f"{key} eq {value}")
                else:
                    clauses.append(f"{key} eq '{escaped}'")
            params["$filter"] = " and ".join(clauses)

        if expand:
            params["$expand"] = ",".join(expand)

        if orderby:
            params["$orderby"] = orderby

        if top is not None:
            params["$top"] = str(top)

        if skip is not None:
            params["$skip"] = str(skip)

        return params

    async def get_list(
        self,
        endpoint: str,
        filters: dict[str, str] | None = None,
        expand: list[str] | None = None,
        orderby: str | None = None,
        top: int = 1000,
        max_total: int = 5000,
    ) -> list[dict[str, Any]]:
        """Fetch a list endpoint with automatic pagination."""
        page_size = min(top, 1000)
        all_results: list[dict[str, Any]] = []
        skip = 0

        while len(all_results) < max_total:
            params = self.build_odata_params(
                filters=filters,
                expand=expand,
                orderby=orderby,
                top=page_size,
                skip=skip if skip > 0 else None,
            )
            # Build query string manually to avoid percent-encoding OData special chars
            if params:
                query_string = "&".join(f"{k}={v}" for k, v in params.items())
                full_endpoint = f"{endpoint}?{query_string}"
            else:
                full_endpoint = endpoint
            raw = await self.get(full_endpoint)
            # Handle paginated response format: {"Values": [...], "TotalCount": N}
            if isinstance(raw, dict) and "Values" in raw:
                page = raw["Values"]
            elif isinstance(raw, list):
                page = raw
            else:
                page = [raw]

            all_results.extend(page)

            if len(page) < page_size:
                break

            skip += page_size

        return all_results[:max_total]
