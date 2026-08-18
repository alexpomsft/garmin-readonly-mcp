"""Command-line entry points for authentication and synchronization."""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from .auth import authenticate
from .paths import StatePaths
from .sync import synchronize
from .validation import parse_date


def _state_dir_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--state-dir", type=Path, default=StatePaths.default().root)
    return parser


def auth_main() -> None:
    """Run one-time interactive authentication without echoing secrets."""
    args = _state_dir_parser("garmin-readonly-auth").parse_args()
    try:
        authenticate(StatePaths.from_root(args.state_dir).tokens)
    except Exception:
        print("Garmin authentication failed", file=sys.stderr)
        raise SystemExit(1) from None


def _bounded_days(value: str) -> int:
    days = int(value)
    if not 1 <= days <= 31:
        raise argparse.ArgumentTypeError("days must be between 1 and 31")
    return days


def sync_main() -> None:
    """Synchronize up to 31 days into the normalized private cache."""
    parser = _state_dir_parser("garmin-readonly-sync")
    parser.add_argument("--end-date", type=parse_date, default=date.today())
    parser.add_argument("--days", type=_bounded_days, default=2)
    args = parser.parse_args()
    paths = StatePaths.from_root(args.state_dir)
    dates = [
        (args.end_date - timedelta(days=offset)).isoformat()
        for offset in reversed(range(args.days))
    ]
    try:
        synchronize(paths.tokens, paths.cache, dates)
    except Exception:
        print("Garmin synchronization failed", file=sys.stderr)
        raise SystemExit(1) from None
