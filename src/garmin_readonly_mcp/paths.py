"""Local state paths for tokens and normalized cache."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StatePaths:
    root: Path
    tokens: Path
    cache: Path

    @classmethod
    def from_root(cls, root: Path) -> "StatePaths":
        expanded = root.expanduser()
        return cls(expanded, expanded / "tokens", expanded / "cache.sqlite3")

    @classmethod
    def default(
        cls,
        *,
        environ: Mapping[str, str] = os.environ,
        home: Path | None = None,
    ) -> "StatePaths":
        configured = environ.get("GARMIN_READONLY_HOME")
        if configured:
            return cls.from_root(Path(configured))
        data_home = environ.get("XDG_DATA_HOME")
        root = Path(data_home) if data_home else (home or Path.home()) / ".local" / "share"
        return cls.from_root(root / "garmin-readonly-mcp")
