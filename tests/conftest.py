"""Shared test fixtures."""

import pytest

from pension_pro_mcp.client import PensionProClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> PensionProClient:
    monkeypatch.setenv("PENSION_PRO_API_KEY", "test-key")
    monkeypatch.setenv("PENSION_PRO_USERNAME", "test-user")
    return PensionProClient()
