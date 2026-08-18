from pathlib import Path

import pytest

from garmin_readonly_mcp import cli


def test_auth_main_uses_selected_state_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    called: list[Path] = []
    monkeypatch.setattr(cli, "authenticate", called.append)
    monkeypatch.setattr("sys.argv", ["garmin-readonly-auth", "--state-dir", str(tmp_path)])

    cli.auth_main()

    assert called == [tmp_path / "tokens"]


def test_auth_main_sanitizes_provider_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(_: Path) -> None:
        raise RuntimeError("upstream included private account details")

    monkeypatch.setattr(cli, "authenticate", fail)
    monkeypatch.setattr("sys.argv", ["garmin-readonly-auth", "--state-dir", str(tmp_path)])

    with pytest.raises(SystemExit, match="1"):
        cli.auth_main()

    captured = capsys.readouterr()
    assert captured.err == "Garmin authentication failed\n"
    assert "private account" not in captured.err


def test_sync_main_syncs_bounded_date_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[Path, Path, list[str]]] = []
    monkeypatch.setattr(
        cli,
        "synchronize",
        lambda tokens, cache, dates: calls.append((tokens, cache, list(dates))),
        raising=False,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "garmin-readonly-sync",
            "--state-dir",
            str(tmp_path),
            "--end-date",
            "2026-08-18",
            "--days",
            "2",
        ],
    )

    cli.sync_main()

    assert calls == [
        (
            tmp_path / "tokens",
            tmp_path / "cache.sqlite3",
            ["2026-08-17", "2026-08-18"],
        )
    ]


def test_sync_main_sanitizes_provider_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*_: object) -> None:
        raise RuntimeError("token and private Garmin response")

    monkeypatch.setattr(cli, "synchronize", fail)
    monkeypatch.setattr(
        "sys.argv", ["garmin-readonly-sync", "--state-dir", str(tmp_path)]
    )

    with pytest.raises(SystemExit, match="1"):
        cli.sync_main()

    assert capsys.readouterr().err == "Garmin synchronization failed\n"
