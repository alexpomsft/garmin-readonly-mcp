from datetime import date
from pathlib import Path

import pytest

from garmin_readonly_mcp.cache import Cache
from garmin_readonly_mcp.service import ReadOnlyService


def _cache(tmp_path: Path) -> Cache:
    cache = Cache(tmp_path / "cache.sqlite3")
    cache.initialize()
    return cache


def test_service_returns_daily_activity_from_normalized_cache(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    item = {
        "date": "2026-08-18",
        "total_kcal": 2487.0,
        "active_kcal": 612.0,
        "bmr_kcal": 1875.0,
        "steps": 10_432,
        "resting_hr_bpm": 54.0,
    }
    cache.upsert_daily_activity(item)

    assert ReadOnlyService(cache).get_daily_activity("2026-08-18") == item


def test_service_rejects_invalid_dates_before_cache_access(tmp_path: Path) -> None:
    service = ReadOnlyService(_cache(tmp_path))

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        service.get_daily_activity("yesterday")


def test_service_returns_only_activities_in_bounded_window(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    cache.upsert_activities(
        [
            {
                "started_at": "2026-08-17T06:30:00Z",
                "activity_type": "running",
                "duration_seconds": 1800.0,
                "distance_meters": 5000.0,
                "calories_kcal": 400.0,
            },
            {
                "started_at": "2026-08-16T06:30:00Z",
                "activity_type": "walking",
                "duration_seconds": 1200.0,
                "distance_meters": 1500.0,
                "calories_kcal": 90.0,
            },
        ]
    )
    service = ReadOnlyService(cache, today=lambda: date(2026, 8, 18))

    assert service.get_recent_activities(2) == [
        {
            "started_at": "2026-08-17T06:30:00Z",
            "activity_type": "running",
            "duration_seconds": 1800.0,
            "distance_meters": 5000.0,
            "calories_kcal": 400.0,
        }
    ]


def test_service_returns_recovery_summary(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    item = {
        "date": "2026-08-18",
        "sleep_seconds": 26_400.0,
        "sleep_score": 82.0,
        "body_battery": 73.0,
        "hrv_ms": 47.0,
        "hrv_status": "BALANCED",
        "training_readiness_score": 71.0,
    }
    cache.upsert_recovery(item)

    assert ReadOnlyService(cache).get_recovery_summary("2026-08-18") == item
