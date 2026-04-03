"""PensionPro API client."""

import os

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
