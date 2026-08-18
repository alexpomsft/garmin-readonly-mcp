import asyncio
from pathlib import Path

import pytest

from garmin_readonly_mcp.cache import Cache
from garmin_readonly_mcp.server import build_server, create_server, main
from garmin_readonly_mcp.service import ReadOnlyService


def test_mcp_exposes_only_three_read_only_tools_with_closed_schemas(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache.sqlite3")
    cache.initialize()
    server = create_server(ReadOnlyService(cache))

    tools = asyncio.run(server.list_tools())

    assert [tool.name for tool in tools] == [
        "get_daily_activity",
        "get_recent_activities",
        "get_recovery_summary",
    ]
    assert all(tool.inputSchema.get("additionalProperties") is False for tool in tools)


def test_mcp_rejects_undeclared_arguments_without_echoing_values(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache.sqlite3")
    cache.initialize()
    server = create_server(ReadOnlyService(cache))

    with pytest.raises(Exception, match="^Garmin tool call failed$") as captured:
        asyncio.run(
            server.call_tool(
                "get_daily_activity",
                {"date": "2026-08-18", "password": "should-never-leak"},
            )
        )
    assert "should-never-leak" not in str(captured.value)


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("get_recent_activities", {"days": "2"}),
        ("get_recent_activities", {"days": 2.0}),
        ("get_recent_activities", {"days": True}),
        ("get_daily_activity", {"date": 20260818}),
        ("get_recovery_summary", {"date": False}),
    ],
)
def test_mcp_rejects_coercible_argument_types_without_reflecting_values(
    tmp_path: Path, tool: str, arguments: dict[str, object]
) -> None:
    cache = Cache(tmp_path / "cache.sqlite3")
    cache.initialize()
    server = create_server(ReadOnlyService(cache))

    with pytest.raises(Exception, match="^Garmin tool call failed$") as captured:
        asyncio.run(server.call_tool(tool, arguments))
    assert all(str(value) not in str(captured.value) for value in arguments.values())


def test_build_server_rejects_group_readable_cache(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "cache.sqlite3")
    cache.initialize()
    cache.path.chmod(0o640)

    with pytest.raises(ValueError, match="owner-only"):
        build_server(cache.path)


def test_mcp_rejects_cache_replaced_after_server_construction(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.sqlite3"
    original = Cache(cache_path)
    original.initialize()
    original.upsert_daily_activity(
        {
            "date": "2026-08-18",
            "total_kcal": 1.0,
            "active_kcal": 1.0,
            "bmr_kcal": 1.0,
            "steps": 1,
            "resting_hr_bpm": None,
        }
    )
    server = build_server(cache_path)

    replacement_path = tmp_path / "replacement.sqlite3"
    replacement = Cache(replacement_path)
    replacement.initialize()
    replacement.upsert_daily_activity(
        {
            "date": "2026-08-18",
            "total_kcal": 999.0,
            "active_kcal": 999.0,
            "bmr_kcal": 999.0,
            "steps": 999,
            "resting_hr_bpm": None,
        }
    )
    replacement_path.replace(cache_path)

    with pytest.raises(Exception, match="^Garmin tool call failed$"):
        asyncio.run(server.call_tool("get_daily_activity", {"date": "2026-08-18"}))


def test_main_sanitizes_startup_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GARMIN_READONLY_HOME", str(tmp_path))

    with pytest.raises(SystemExit, match="1"):
        main()

    assert capsys.readouterr().err == "Garmin read-only MCP failed to start\n"
