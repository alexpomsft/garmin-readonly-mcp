import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from garmin_readonly_mcp.cache import Cache
from garmin_readonly_mcp.sync import sync_date, synchronize


class FakeGarmin:
    def __init__(self) -> None:
        self.login_paths: list[str] = []

    def login(self, tokenstore: str) -> None:
        self.login_paths.append(tokenstore)

    def get_stats(self, date: str) -> dict[str, Any]:
        return {
            "totalKilocalories": 2487,
            "activeKilocalories": 612,
            "bmrKilocalories": 1875,
            "totalSteps": 10_432,
            "restingHeartRate": 54,
        }

    def get_activities_by_date(self, start: str, end: str) -> list[dict[str, Any]]:
        return [
            {
                "activityId": 123,
                "activityType": {"typeKey": "running"},
                "startTimeGMT": "2026-08-18 06:30:00",
                "duration": 1800,
                "distance": 5000,
                "calories": 400,
                "startLatitude": 59.9,
            }
        ]

    def get_sleep_data(self, date: str) -> dict[str, Any]:
        return {}

    def get_body_battery(self, start: str, end: str) -> list[dict[str, Any]]:
        return []

    def get_hrv_data(self, date: str) -> dict[str, Any]:
        return {}

    def get_training_readiness(self, date: str) -> list[dict[str, Any]]:
        return []


def make_private_tokens(token_dir: Path) -> None:
    token_dir.mkdir(mode=0o700)
    path = token_dir / "garmin_tokens.json"
    path.write_text("{}", encoding="utf-8")
    path.chmod(0o600)


def test_sync_date_writes_only_normalized_records(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "garmin.sqlite3")
    cache.initialize()

    sync_date(FakeGarmin(), cache, "2026-08-18")

    assert cache.get_daily_activity("2026-08-18") is not None
    assert cache.get_activities_since("2026-08-18T00:00:00Z") == [
        {
            "started_at": "2026-08-18T06:30:00Z",
            "activity_type": "running",
            "duration_seconds": 1800.0,
            "distance_meters": 5000.0,
            "calories_kcal": 400.0,
        }
    ]
    assert cache.get_recovery("2026-08-18") == {
        "date": "2026-08-18",
        "sleep_seconds": None,
        "sleep_score": None,
        "body_battery": None,
        "hrv_ms": None,
        "hrv_status": None,
        "training_readiness_score": None,
    }


def test_sync_date_removes_activities_deleted_upstream(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "garmin.sqlite3")
    cache.initialize()
    client = FakeGarmin()
    sync_date(client, cache, "2026-08-18")
    client.get_activities_by_date = lambda start, end: []  # type: ignore[method-assign]

    sync_date(client, cache, "2026-08-18")

    assert cache.get_activities_since("2026-08-18T00:00:00Z") == []


def test_sync_date_removes_deleted_positive_offset_activity_by_calendar_date(
    tmp_path: Path,
) -> None:
    cache = Cache(tmp_path / "garmin.sqlite3")
    cache.initialize()
    client = FakeGarmin()
    client.get_activities_by_date = lambda start, end: [  # type: ignore[method-assign]
        {
            "activityType": {"typeKey": "running"},
            "startTimeGMT": "2026-08-18T00:30:00+02:00",
            "duration": 1800,
            "distance": 5000,
            "calories": 400,
        }
    ]
    sync_date(client, cache, "2026-08-18")
    client.get_activities_by_date = lambda start, end: []  # type: ignore[method-assign]

    sync_date(client, cache, "2026-08-18")

    assert cache.get_activities_since("2026-08-17T00:00:00Z") == []


def test_sync_date_rolls_back_all_records_when_one_write_fails(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "garmin.sqlite3")
    cache.initialize()
    client = FakeGarmin()
    sync_date(client, cache, "2026-08-18")
    with sqlite3.connect(cache.path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_recovery BEFORE UPDATE ON recovery
            BEGIN SELECT RAISE(ABORT, 'forced failure'); END
            """
        )
    client.get_stats = lambda date: {  # type: ignore[method-assign]
        "totalKilocalories": 999,
        "activeKilocalories": 1,
        "bmrKilocalories": 1,
        "totalSteps": 1,
    }
    client.get_activities_by_date = lambda start, end: []  # type: ignore[method-assign]

    with pytest.raises(sqlite3.IntegrityError, match="forced failure"):
        sync_date(client, cache, "2026-08-18")

    assert cache.get_daily_activity("2026-08-18")["total_kcal"] == 2487.0  # type: ignore[index]
    assert len(cache.get_activities_since("2026-08-18T00:00:00Z")) == 1


def test_synchronize_loads_only_local_tokens_and_writes_private_cache(tmp_path: Path) -> None:
    client = FakeGarmin()
    token_dir = tmp_path / "tokens"
    make_private_tokens(token_dir)
    cache_path = tmp_path / "cache.sqlite3"

    synchronize(
        token_dir,
        cache_path,
        ["2026-08-18"],
        client_factory=lambda: client,
    )

    assert client.login_paths == [str(token_dir)]
    assert Cache(cache_path).get_daily_activity("2026-08-18") is not None
    assert cache_path.stat().st_mode & 0o777 == 0o600


def test_synchronize_prunes_records_outside_requested_date_range(tmp_path: Path) -> None:
    token_dir = tmp_path / "tokens"
    make_private_tokens(token_dir)
    cache_path = tmp_path / "cache.sqlite3"
    cache = Cache(cache_path)
    cache.initialize()
    sync_date(FakeGarmin(), cache, "2026-08-17")

    synchronize(
        token_dir,
        cache_path,
        ["2026-08-18"],
        client_factory=FakeGarmin,
    )

    assert cache.get_daily_activity("2026-08-17") is None
    assert cache.get_recovery("2026-08-17") is None


def test_synchronize_keeps_negative_offset_activity_by_calendar_date(tmp_path: Path) -> None:
    token_dir = tmp_path / "tokens"
    make_private_tokens(token_dir)
    cache_path = tmp_path / "cache.sqlite3"
    client = FakeGarmin()
    client.get_activities_by_date = lambda start, end: [  # type: ignore[method-assign]
        {
            "activityType": {"typeKey": "running"},
            "startTimeGMT": "2026-08-18T22:30:00-04:00",
            "duration": 1800,
            "distance": 5000,
            "calories": 400,
        }
    ]

    synchronize(
        token_dir,
        cache_path,
        ["2026-08-18"],
        client_factory=lambda: client,
    )

    assert Cache(cache_path).get_activities_since("2026-08-19T00:00:00Z") == [
        {
            "started_at": "2026-08-19T02:30:00Z",
            "activity_type": "running",
            "duration_seconds": 1800.0,
            "distance_meters": 5000.0,
            "calories_kcal": 400.0,
        }
    ]


def test_synchronize_rejects_nonprivate_token_directory(tmp_path: Path) -> None:
    token_dir = tmp_path / "tokens"
    token_dir.mkdir(mode=0o755)
    cache_path = tmp_path / "cache.sqlite3"
    factory_called = False

    def factory() -> FakeGarmin:
        nonlocal factory_called
        factory_called = True
        return FakeGarmin()

    with pytest.raises(ValueError, match="owner-only"):
        synchronize(token_dir, cache_path, ["2026-08-18"], client_factory=factory)

    assert factory_called is False


def test_synchronize_rejects_special_token_entries(tmp_path: Path) -> None:
    token_dir = tmp_path / "tokens"
    token_dir.mkdir(mode=0o700)
    os.mkfifo(token_dir / "oauth1_token.json", mode=0o600)

    with pytest.raises(ValueError, match="regular files"):
        synchronize(
            token_dir,
            tmp_path / "cache.sqlite3",
            ["2026-08-18"],
            client_factory=lambda: pytest.fail("factory must not be called"),
        )


def test_synchronize_requires_reusable_token_material(tmp_path: Path) -> None:
    token_dir = tmp_path / "tokens"
    token_dir.mkdir(mode=0o700)

    with pytest.raises(ValueError, match="reusable token material"):
        synchronize(
            token_dir,
            tmp_path / "cache.sqlite3",
            ["2026-08-18"],
            client_factory=lambda: pytest.fail("factory must not be called"),
        )
