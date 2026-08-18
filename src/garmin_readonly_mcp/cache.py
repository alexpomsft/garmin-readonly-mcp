"""Normalized SQLite cache shared by the sync worker and MCP server."""

import os
import sqlite3
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path

from .security import reject_symlink_ancestors, require_private_directory


class Cache:
    """Store and retrieve only the approved normalized Garmin fields."""

    def __init__(
        self,
        path: Path,
        *,
        readonly: bool = False,
        expected_identity: tuple[int, int, int, int] | None = None,
    ) -> None:
        self.path = path.expanduser()
        self.readonly = readonly
        self.expected_identity = expected_identity

    @classmethod
    def for_readonly(cls, path: Path) -> "Cache":
        """Pin the validated parent and cache identities for cache-only reads."""
        expanded = path.expanduser()
        reject_symlink_ancestors(expanded)
        require_private_directory(expanded.parent)
        parent = expanded.parent.stat()
        metadata = expanded.stat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077
        ):
            raise ValueError("Garmin cache must be an owner-only regular file")
        return cls(
            expanded,
            readonly=True,
            expected_identity=(parent.st_dev, parent.st_ino, metadata.st_dev, metadata.st_ino),
        )

    def _connect(self) -> sqlite3.Connection:
        if self.readonly:
            connection = self._connect_readonly()
        else:
            connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _connect_readonly(self) -> sqlite3.Connection:
        reject_symlink_ancestors(self.path)
        require_private_directory(self.path.parent)
        parent = self.path.parent.stat()
        descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            metadata = os.fstat(descriptor)
            identity = (parent.st_dev, parent.st_ino, metadata.st_dev, metadata.st_ino)
            if (
                identity != self.expected_identity
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or metadata.st_mode & 0o077
            ):
                raise ValueError("Garmin cache changed after startup")
            connection = sqlite3.connect(f"file:/proc/self/fd/{descriptor}?mode=ro", uri=True)
        finally:
            os.close(descriptor)
        return connection

    def initialize(self) -> None:
        reject_symlink_ancestors(self.path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        require_private_directory(self.path.parent)
        if self.path.exists():
            metadata = self.path.stat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or metadata.st_mode & 0o077
            ):
                raise ValueError("cache must be an owner-only regular file")
        else:
            descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600,
            )
            os.close(descriptor)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_activity (
                    date TEXT PRIMARY KEY,
                    total_kcal REAL NOT NULL,
                    active_kcal REAL NOT NULL,
                    bmr_kcal REAL NOT NULL,
                    steps INTEGER NOT NULL,
                    resting_hr_bpm REAL
                ) STRICT
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS activities (
                    source_date TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    activity_type TEXT NOT NULL,
                    duration_seconds REAL NOT NULL,
                    distance_meters REAL NOT NULL,
                    calories_kcal REAL NOT NULL,
                    PRIMARY KEY (started_at, activity_type, duration_seconds)
                ) STRICT
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS recovery (
                    date TEXT PRIMARY KEY,
                    sleep_seconds REAL,
                    sleep_score REAL,
                    body_battery REAL,
                    hrv_ms REAL,
                    hrv_status TEXT,
                    training_readiness_score REAL
                ) STRICT
                """
            )


    def upsert_daily_activity(self, item: Mapping[str, object]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO daily_activity
                    (date, total_kcal, active_kcal, bmr_kcal, steps, resting_hr_bpm)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    total_kcal = excluded.total_kcal,
                    active_kcal = excluded.active_kcal,
                    bmr_kcal = excluded.bmr_kcal,
                    steps = excluded.steps,
                    resting_hr_bpm = excluded.resting_hr_bpm
                """,
                (
                    item["date"],
                    item["total_kcal"],
                    item["active_kcal"],
                    item["bmr_kcal"],
                    item["steps"],
                    item["resting_hr_bpm"],
                ),
            )

    def get_daily_activity(self, date: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT date, total_kcal, active_kcal, bmr_kcal, steps, resting_hr_bpm
                FROM daily_activity
                WHERE date = ?
                """,
                (date,),
            ).fetchone()
        return dict(row) if row is not None else None

    def upsert_activities(self, items: Sequence[Mapping[str, object]]) -> None:
        rows = [
            (
                item.get("source_date", str(item["started_at"])[:10]),
                item["started_at"],
                item["activity_type"],
                item["duration_seconds"],
                item["distance_meters"],
                item["calories_kcal"],
            )
            for item in items
        ]
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO activities
                    (source_date, started_at, activity_type, duration_seconds, distance_meters,
                     calories_kcal)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(started_at, activity_type, duration_seconds) DO UPDATE SET
                    source_date = excluded.source_date,
                    distance_meters = excluded.distance_meters,
                    calories_kcal = excluded.calories_kcal
                """,
                rows,
            )

    def replace_date(
        self,
        date: str,
        daily: Mapping[str, object],
        activities: Sequence[Mapping[str, object]],
        recovery: Mapping[str, object],
    ) -> None:
        """Replace all normalized records belonging to one date."""
        activity_rows = [
            (
                date,
                item["started_at"],
                item["activity_type"],
                item["duration_seconds"],
                item["distance_meters"],
                item["calories_kcal"],
            )
            for item in activities
        ]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO daily_activity
                    (date, total_kcal, active_kcal, bmr_kcal, steps, resting_hr_bpm)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    total_kcal = excluded.total_kcal,
                    active_kcal = excluded.active_kcal,
                    bmr_kcal = excluded.bmr_kcal,
                    steps = excluded.steps,
                    resting_hr_bpm = excluded.resting_hr_bpm
                """,
                (
                    daily["date"],
                    daily["total_kcal"],
                    daily["active_kcal"],
                    daily["bmr_kcal"],
                    daily["steps"],
                    daily["resting_hr_bpm"],
                ),
            )
            connection.execute(
                "DELETE FROM activities WHERE source_date = ?",
                (date,),
            )
            connection.executemany(
                """
                INSERT INTO activities
                    (source_date, started_at, activity_type, duration_seconds, distance_meters,
                     calories_kcal)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(started_at, activity_type, duration_seconds) DO UPDATE SET
                    source_date = excluded.source_date,
                    distance_meters = excluded.distance_meters,
                    calories_kcal = excluded.calories_kcal
                """,
                activity_rows,
            )
            connection.execute(
                """
                INSERT INTO recovery
                    (date, sleep_seconds, sleep_score, body_battery, hrv_ms, hrv_status,
                     training_readiness_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    sleep_seconds = excluded.sleep_seconds,
                    sleep_score = excluded.sleep_score,
                    body_battery = excluded.body_battery,
                    hrv_ms = excluded.hrv_ms,
                    hrv_status = excluded.hrv_status,
                    training_readiness_score = excluded.training_readiness_score
                """,
                (
                    recovery["date"],
                    recovery["sleep_seconds"],
                    recovery["sleep_score"],
                    recovery["body_battery"],
                    recovery["hrv_ms"],
                    recovery["hrv_status"],
                    recovery["training_readiness_score"],
                ),
            )

    def get_activities_since(self, started_at: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT started_at, activity_type, duration_seconds, distance_meters, calories_kcal
                FROM activities
                WHERE started_at >= ?
                ORDER BY started_at DESC
                """,
                (started_at,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_recovery(self, item: Mapping[str, object]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO recovery
                    (date, sleep_seconds, sleep_score, body_battery, hrv_ms, hrv_status,
                     training_readiness_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    sleep_seconds = excluded.sleep_seconds,
                    sleep_score = excluded.sleep_score,
                    body_battery = excluded.body_battery,
                    hrv_ms = excluded.hrv_ms,
                    hrv_status = excluded.hrv_status,
                    training_readiness_score = excluded.training_readiness_score
                """,
                (
                    item["date"],
                    item["sleep_seconds"],
                    item["sleep_score"],
                    item["body_battery"],
                    item["hrv_ms"],
                    item["hrv_status"],
                    item["training_readiness_score"],
                ),
            )

    def get_recovery(self, date: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT date, sleep_seconds, sleep_score, body_battery, hrv_ms, hrv_status,
                       training_readiness_score
                FROM recovery
                WHERE date = ?
                """,
                (date,),
            ).fetchone()
        return dict(row) if row is not None else None

    def prune_to_date_range(self, start: str, end: str) -> None:
        """Remove cached records outside the explicitly synchronized range."""
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM daily_activity WHERE date < ? OR date > ?", (start, end)
            )
            connection.execute("DELETE FROM recovery WHERE date < ? OR date > ?", (start, end))
            connection.execute(
                "DELETE FROM activities WHERE source_date < ? OR source_date > ?",
                (start, end),
            )
