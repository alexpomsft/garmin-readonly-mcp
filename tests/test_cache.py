import sqlite3
from pathlib import Path

import pytest

from garmin_readonly_mcp.cache import Cache


def test_cache_file_is_owner_only_before_sqlite_opens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache_path = tmp_path / "state" / "cache.sqlite3"
    real_connect = sqlite3.connect

    def checked_connect(database: str | Path) -> sqlite3.Connection:
        assert cache_path.stat().st_mode & 0o777 == 0o600
        return real_connect(database)

    monkeypatch.setattr(sqlite3, "connect", checked_connect)
    Cache(cache_path).initialize()


def test_cache_round_trips_only_normalized_daily_activity(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "garmin.sqlite3")
    cache.initialize()
    cache.upsert_daily_activity(
        {
            "date": "2026-08-18",
            "total_kcal": 2487.0,
            "active_kcal": 612.0,
            "bmr_kcal": 1875.0,
            "steps": 10_432,
            "resting_hr_bpm": 54.0,
        }
    )

    assert cache.get_daily_activity("2026-08-18") == {
        "date": "2026-08-18",
        "total_kcal": 2487.0,
        "active_kcal": 612.0,
        "bmr_kcal": 1875.0,
        "steps": 10_432,
        "resting_hr_bpm": 54.0,
    }
    assert (tmp_path / "garmin.sqlite3").stat().st_mode & 0o777 == 0o600


def test_cache_accepts_unavailable_resting_heart_rate(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "garmin.sqlite3")
    cache.initialize()
    item = {
        "date": "2026-08-18",
        "total_kcal": 2487.0,
        "active_kcal": 612.0,
        "bmr_kcal": 1875.0,
        "steps": 10_432,
        "resting_hr_bpm": None,
    }

    cache.upsert_daily_activity(item)

    assert cache.get_daily_activity("2026-08-18") == item


def test_cache_round_trips_recent_activities_without_identifiers(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "garmin.sqlite3")
    cache.initialize()
    cache.upsert_activities(
        [
            {
                "started_at": "2026-08-18T06:30:00Z",
                "activity_type": "running",
                "duration_seconds": 1800.5,
                "distance_meters": 5123.4,
                "calories_kcal": 421.0,
            }
        ]
    )

    assert cache.get_activities_since("2026-08-17T00:00:00Z") == [
        {
            "started_at": "2026-08-18T06:30:00Z",
            "activity_type": "running",
            "duration_seconds": 1800.5,
            "distance_meters": 5123.4,
            "calories_kcal": 421.0,
        }
    ]


def test_cache_round_trips_recovery_summary(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "garmin.sqlite3")
    cache.initialize()
    cache.upsert_recovery(
        {
            "date": "2026-08-18",
            "sleep_seconds": 26_400.0,
            "sleep_score": 82.0,
            "body_battery": 73.0,
            "hrv_ms": 47.0,
            "hrv_status": "BALANCED",
            "training_readiness_score": 71.0,
        }
    )

    assert cache.get_recovery("2026-08-18") == {
        "date": "2026-08-18",
        "sleep_seconds": 26_400.0,
        "sleep_score": 82.0,
        "body_battery": 73.0,
        "hrv_ms": 47.0,
        "hrv_status": "BALANCED",
        "training_readiness_score": 71.0,
    }


def test_cache_accepts_unavailable_recovery_metrics(tmp_path: Path) -> None:
    cache = Cache(tmp_path / "garmin.sqlite3")
    cache.initialize()
    item = {
        "date": "2026-08-18",
        "sleep_seconds": None,
        "sleep_score": None,
        "body_battery": None,
        "hrv_ms": None,
        "hrv_status": None,
        "training_readiness_score": None,
    }

    cache.upsert_recovery(item)

    assert cache.get_recovery("2026-08-18") == item
