"""Strict input validation shared by CLI and MCP surfaces."""

import re
from datetime import date


def parse_date(value: str) -> date:
    """Parse only canonical ISO calendar dates."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date must use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must use YYYY-MM-DD") from exc
