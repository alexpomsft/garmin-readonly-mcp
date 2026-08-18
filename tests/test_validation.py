import pytest

from garmin_readonly_mcp.validation import parse_date


def test_parse_date_rejects_noncanonical_values() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        parse_date("2026-8-18")
