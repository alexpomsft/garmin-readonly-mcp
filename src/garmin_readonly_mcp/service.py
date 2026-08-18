"""Data-only service exposed through MCP."""

from collections.abc import Callable
from datetime import date, timedelta

from .cache import Cache
from .validation import parse_date


class ReadOnlyService:
    """Read normalized data without importing the Garmin network client."""

    def __init__(self, cache: Cache, *, today: Callable[[], date] = date.today) -> None:
        self.cache = cache
        self.today = today

    def get_daily_activity(self, date: str) -> dict[str, object]:
        parse_date(date)
        try:
            item = self.cache.get_daily_activity(date)
        except Exception:
            raise RuntimeError("Garmin cache unavailable") from None
        if item is None:
            raise LookupError("Daily activity not available")
        return item

    def get_recent_activities(self, days: int = 7) -> list[dict[str, object]]:
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 31:
            raise ValueError("days must be between 1 and 31")
        since = self.today() - timedelta(days=days - 1)
        try:
            return self.cache.get_activities_since(f"{since.isoformat()}T00:00:00Z")
        except Exception:
            raise RuntimeError("Garmin cache unavailable") from None

    def get_recovery_summary(self, date: str) -> dict[str, object]:
        parse_date(date)
        try:
            item = self.cache.get_recovery(date)
        except Exception:
            raise RuntimeError("Garmin cache unavailable") from None
        if item is None:
            raise LookupError("Recovery summary not available")
        return item
