"""PensionPro API client."""

import json
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
            headers={"apikey-username": f"{api_key}|{username}"},
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
        content = json.dumps(data).encode() if data is not None else None
        headers = {"Content-Type": "application/json"} if content is not None else {}
        response = await self._http.post(endpoint, content=content, headers=headers)
        return await self._handle_response(response, endpoint)

    async def put(self, endpoint: str, data: dict[str, Any] | None = None) -> Any:
        """Send a PUT request with an optional JSON body."""
        content = json.dumps(data).encode() if data is not None else None
        headers = {"Content-Type": "application/json"} if content is not None else {}
        response = await self._http.put(endpoint, content=content, headers=headers)
        return await self._handle_response(response, endpoint)

    async def delete(self, endpoint: str) -> Any:
        """Send a DELETE request."""
        response = await self._http.delete(endpoint)
        return await self._handle_response(response, endpoint)
