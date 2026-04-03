"""PensionPro MCP Server entry point."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from pension_pro_mcp.client import PensionProClient


@dataclass
class AppContext:
    """Shared application context available to all tools."""

    client: PensionProClient


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage the PensionPro HTTP client lifecycle."""
    client = PensionProClient()
    try:
        yield AppContext(client=client)
    finally:
        await client.close()


mcp = FastMCP(
    "PensionPro",
    lifespan=app_lifespan,
)


def main() -> None:
    """CLI entry point."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
