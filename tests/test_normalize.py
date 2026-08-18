import pytest

from garmin_readonly_mcp.normalize import (
    normalize_activities,
    normalize_daily_activity,
    normalize_recovery,
)


def test_normalize_daily_activity_returns_only_canonical_fields() -> None:
    raw = {
        "calendarDate": "2026-08-18",
        "totalKilocalories": 2487.0,
        "activeKilocalories": 612.0,
        "bmrKilocalories": 1875.0,
        "totalSteps": 10_432,
        "restingHeartRate": 54,
        "displayName": "private-user",
        "privacyProtected": False,
    }

    assert normalize_daily_activity(raw, "2026-08-18") == {
        "date": "2026-08-18",
        "total_kcal": 2487.0,
        "active_kcal": 612.0,
        "bmr_kcal": 1875.0,
        "steps": 10_432,
        "resting_hr_bpm": 54.0,
    }


def test_normalize_daily_activity_rejects_non_finite_values() -> None:
    raw = {
        "totalKilocalories": "nan",
        "activeKilocalories": 1,
        "bmrKilocalories": 1,
        "totalSteps": 1,
        "restingHeartRate": 1,
    }

    with pytest.raises(ValueError, match="total_kcal"):
        normalize_daily_activity(raw, "2026-08-18")


def test_normalize_daily_activity_allows_unavailable_resting_heart_rate() -> None:
    raw = {
        "totalKilocalories": 2487,
        "activeKilocalories": 612,
        "bmrKilocalories": 1875,
        "totalSteps": 10_432,
        "restingHeartRate": None,
    }

    assert normalize_daily_activity(raw, "2026-08-18")["resting_hr_bpm"] is None


def test_normalize_activities_strips_ids_names_and_location() -> None:
    raw = [
        {
            "activityId": 12345,
            "activityName": "Secret route",
            "activityType": {"typeKey": "running"},
            "startTimeGMT": "2026-08-18 06:30:00",
            "duration": 1800.5,
            "distance": 5_123.4,
            "calories": 421.0,
            "startLatitude": 59.9,
            "startLongitude": 10.7,
        }
    ]

    assert normalize_activities(raw) == [
        {
            "started_at": "2026-08-18T06:30:00Z",
            "activity_type": "running",
            "duration_seconds": 1800.5,
            "distance_meters": 5123.4,
            "calories_kcal": 421.0,
        }
    ]


def test_normalize_recovery_returns_only_approved_summary_fields() -> None:
    sleep = {
        "dailySleepDTO": {
            "sleepTimeSeconds": 26_400,
            "sleepScores": {"overall": {"value": 82}},
            "sleepStartTimestampGMT": 1_755_480_000_000,
        },
        "userProfile": {"name": "private"},
    }
    body_battery = [{"bodyBatteryValuesArray": [[1_755_500_000_000, 73]]}]
    hrv = {"hrvSummary": {"lastNightAvg": 47, "status": "BALANCED"}}
    readiness = [{"score": 71, "inputContext": "AFTER_WAKEUP_RESET"}]

    assert normalize_recovery("2026-08-18", sleep, body_battery, hrv, readiness) == {
        "date": "2026-08-18",
        "sleep_seconds": 26_400.0,
        "sleep_score": 82.0,
        "body_battery": 73.0,
        "hrv_ms": 47.0,
        "hrv_status": "BALANCED",
        "training_readiness_score": 71.0,
    }


def test_normalize_recovery_allows_metrics_unavailable_on_a_device() -> None:
    assert normalize_recovery("2026-08-18", {}, [], {}, []) == {
        "date": "2026-08-18",
        "sleep_seconds": None,
        "sleep_score": None,
        "body_battery": None,
        "hrv_ms": None,
        "hrv_status": None,
        "training_readiness_score": None,
    }


def test_normalize_recovery_allows_absent_hrv_response() -> None:
    result = normalize_recovery("2026-08-18", {}, [], None, [])

    assert result["hrv_ms"] is None
    assert result["hrv_status"] is None
