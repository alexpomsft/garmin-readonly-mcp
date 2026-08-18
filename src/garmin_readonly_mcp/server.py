"""Minimal stdio MCP backed only by the normalized local cache."""

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ContentBlock
from pydantic import Strict

from .cache import Cache
from .paths import StatePaths
from .service import ReadOnlyService


class SafeFastMCP(FastMCP):
    """FastMCP variant that never reflects argument values in public errors."""

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Sequence[ContentBlock] | dict[str, Any]:
        try:
            return await super().call_tool(name, arguments)
        except Exception:
            raise ToolError("Garmin tool call failed") from None


def _close_tool_schema(server: FastMCP, name: str) -> None:
    """Reject undeclared arguments and advertise a closed JSON schema."""
    tool = server._tool_manager.get_tool(name)
    if tool is None:  # pragma: no cover - protects against an incompatible MCP SDK
        raise RuntimeError("MCP tool registration failed")
    tool.fn_metadata.arg_model.model_config["extra"] = "forbid"
    tool.fn_metadata.arg_model.model_rebuild(force=True)
    tool.parameters = tool.fn_metadata.arg_model.model_json_schema(by_alias=True)


def create_server(service: ReadOnlyService) -> FastMCP:
    server = SafeFastMCP(
        "garmin-readonly-mcp", instructions="Read-only normalized Garmin summaries"
    )

    @server.tool()
    def get_daily_activity(date: Annotated[str, Strict()]) -> dict[str, object]:
        """Get normalized daily calories, steps, and resting heart rate."""
        return service.get_daily_activity(date)

    @server.tool()
    def get_recent_activities(days: Annotated[int, Strict()] = 7) -> list[dict[str, object]]:
        """Get normalized activity summaries from the last 1–31 days."""
        return service.get_recent_activities(days)

    @server.tool()
    def get_recovery_summary(date: Annotated[str, Strict()]) -> dict[str, object]:
        """Get normalized sleep, Body Battery, HRV, and training readiness."""
        return service.get_recovery_summary(date)

    for name in ("get_daily_activity", "get_recent_activities", "get_recovery_summary"):
        _close_tool_schema(server, name)
    return server


def build_server(cache_path: Path) -> FastMCP:
    """Build a server only for an owner-only, regular cache file."""
    return create_server(ReadOnlyService(Cache.for_readonly(cache_path)))


def main() -> None:
    """Run the cache-only MCP over stdio with a fixed startup error."""
    try:
        build_server(StatePaths.default().cache).run("stdio")
    except Exception:
        print("Garmin read-only MCP failed to start", file=sys.stderr)
        raise SystemExit(1) from None
