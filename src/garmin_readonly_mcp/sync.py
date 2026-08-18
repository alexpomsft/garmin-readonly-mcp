"""Networked sync worker; the MCP server never imports this module."""

import os
import stat
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, cast

from garminconnect import Garmin

from .cache import Cache
from .normalize import normalize_activities, normalize_daily_activity, normalize_recovery
from .security import reject_symlink_ancestors, require_private_directory


class GarminReader(Protocol):
    def login(self, tokenstore: str) -> tuple[str | None, str | None] | None: ...

    def get_stats(self, date: str) -> Mapping[str, Any]: ...

    def get_activities_by_date(
        self, start: str, end: str
    ) -> Sequence[Mapping[str, Any]]: ...

    def get_sleep_data(self, date: str) -> Mapping[str, Any]: ...

    def get_body_battery(self, start: str, end: str) -> Sequence[Mapping[str, Any]]: ...

    def get_hrv_data(self, date: str) -> Mapping[str, Any] | None: ...

    def get_training_readiness(self, date: str) -> Sequence[Mapping[str, Any]]: ...


def sync_date(client: GarminReader, cache: Cache, date: str) -> None:
    """Fetch one day and persist only normalized, approved fields."""
    daily = normalize_daily_activity(client.get_stats(date), date)
    activities = normalize_activities(client.get_activities_by_date(date, date))
    recovery = normalize_recovery(
        date,
        client.get_sleep_data(date),
        client.get_body_battery(date, date),
        client.get_hrv_data(date),
        client.get_training_readiness(date),
    )
    cache.replace_date(date, daily, activities, recovery)


def _garmin_factory() -> GarminReader:
    return cast(GarminReader, Garmin())


def _validate_private_tokens(token_dir: Path) -> None:
    reject_symlink_ancestors(token_dir)
    require_private_directory(token_dir.parent)
    require_private_directory(token_dir)
    for entry in token_dir.iterdir():
        if entry.is_symlink():
            raise ValueError("Garmin token directory must not contain symbolic links")
        metadata = entry.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Garmin token entries must be regular files")
        if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
            raise ValueError("Garmin token material must be owner-only")
    required_tokens = {"garmin_tokens.json"}
    if not required_tokens.issubset(entry.name for entry in token_dir.iterdir()):
        raise ValueError("Garmin reusable token material is unavailable")


def synchronize(
    token_dir: Path,
    cache_path: Path,
    dates: Sequence[str],
    *,
    client_factory: Callable[[], GarminReader] = _garmin_factory,
) -> None:
    """Load local session tokens and synchronize normalized summaries."""
    _validate_private_tokens(token_dir)
    client = client_factory()
    client.login(str(token_dir))
    cache = Cache(cache_path)
    cache.initialize()
    for date in dates:
        sync_date(client, cache, date)
    if dates:
        cache.prune_to_date_range(min(dates), max(dates))
