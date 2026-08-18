"""Garmin Connect data minimization for the local cache."""

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from math import isfinite
from typing import Any


def _finite_number(raw: object, field: str, *, minimum: float = 0) -> float:
    if isinstance(raw, bool):
        raise ValueError(f"{field} must be a finite number")
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not isfinite(value) or value < minimum:
        raise ValueError(f"{field} must be a finite number >= {minimum}")
    return value


def _optional_finite(raw: object, field: str) -> float | None:
    return None if raw is None else _finite_number(raw, field)


def normalize_daily_activity(raw: Mapping[str, Any], date: str) -> dict[str, object]:
    """Return only the daily fields approved for the local cache."""
    steps = _finite_number(raw.get("totalSteps"), "steps")
    if not steps.is_integer():
        raise ValueError("steps must be an integer")
    return {
        "date": date,
        "total_kcal": _finite_number(raw.get("totalKilocalories"), "total_kcal"),
        "active_kcal": _finite_number(raw.get("activeKilocalories"), "active_kcal"),
        "bmr_kcal": _finite_number(raw.get("bmrKilocalories"), "bmr_kcal"),
        "steps": int(steps),
        "resting_hr_bpm": _optional_finite(raw.get("restingHeartRate"), "resting_hr_bpm"),
    }


def _utc_timestamp(raw: object) -> str:
    if not isinstance(raw, str):
        raise ValueError("started_at must be a timestamp")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("started_at must be a timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def normalize_activities(raw_items: Sequence[Mapping[str, Any]]) -> list[dict[str, object]]:
    """Return activity context without names, account IDs, or location data."""
    normalized: list[dict[str, object]] = []
    for raw in raw_items:
        activity_type = raw.get("activityType")
        type_key = activity_type.get("typeKey") if isinstance(activity_type, Mapping) else None
        if not isinstance(type_key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", type_key):
            raise ValueError("activity_type must be a canonical key")
        normalized.append(
            {
                "started_at": _utc_timestamp(raw.get("startTimeGMT")),
                "activity_type": type_key,
                "duration_seconds": _finite_number(raw.get("duration"), "duration_seconds"),
                "distance_meters": _finite_number(raw.get("distance"), "distance_meters"),
                "calories_kcal": _finite_number(raw.get("calories"), "calories_kcal"),
            }
        )
    return normalized


def normalize_recovery(
    date: str,
    sleep: Mapping[str, Any],
    body_battery: Sequence[Mapping[str, Any]],
    hrv: Mapping[str, Any] | None,
    readiness: Sequence[Mapping[str, Any]],
) -> dict[str, object]:
    """Return only sleep and recovery signals approved for the local cache."""
    sleep_dto = sleep.get("dailySleepDTO")
    sleep_dto = sleep_dto if isinstance(sleep_dto, Mapping) else {}
    sleep_scores = sleep_dto.get("sleepScores")
    sleep_scores = sleep_scores if isinstance(sleep_scores, Mapping) else {}
    overall = sleep_scores.get("overall")
    overall = overall if isinstance(overall, Mapping) else {}

    values: list[tuple[float, float]] = []
    for day in body_battery:
        points = day.get("bodyBatteryValuesArray")
        if not isinstance(points, Sequence) or isinstance(points, str | bytes):
            continue
        for point in points:
            if (
                isinstance(point, Sequence)
                and not isinstance(point, str | bytes)
                and len(point) >= 2
            ):
                values.append(
                    (
                        _finite_number(point[0], "body_battery_timestamp"),
                        _finite_number(point[1], "body_battery"),
                    )
                )
    hrv_summary = hrv.get("hrvSummary") if hrv is not None else None
    hrv_summary = hrv_summary if isinstance(hrv_summary, Mapping) else {}
    hrv_status = hrv_summary.get("status")
    if hrv_status is not None and (
        not isinstance(hrv_status, str) or not re.fullmatch(r"[A-Z_]{1,32}", hrv_status)
    ):
        raise ValueError("hrv_status must be a canonical key")

    morning = next(
        (item for item in readiness if item.get("inputContext") == "AFTER_WAKEUP_RESET"),
        readiness[0] if readiness else {},
    )
    return {
        "date": date,
        "sleep_seconds": _optional_finite(sleep_dto.get("sleepTimeSeconds"), "sleep_seconds"),
        "sleep_score": _optional_finite(overall.get("value"), "sleep_score"),
        "body_battery": max(values)[1] if values else None,
        "hrv_ms": _optional_finite(hrv_summary.get("lastNightAvg"), "hrv_ms"),
        "hrv_status": hrv_status,
        "training_readiness_score": _optional_finite(
            morning.get("score"), "training_readiness_score"
        ),
    }
