from pathlib import Path

from garmin_readonly_mcp.paths import StatePaths


def test_state_paths_use_explicit_root_without_credentials(tmp_path: Path) -> None:
    paths = StatePaths.from_root(tmp_path / "state")

    assert paths.tokens == tmp_path / "state" / "tokens"
    assert paths.cache == tmp_path / "state" / "cache.sqlite3"


def test_state_paths_allow_nonsecret_environment_override(tmp_path: Path) -> None:
    paths = StatePaths.default(
        environ={"GARMIN_READONLY_HOME": str(tmp_path / "garmin")},
        home=tmp_path,
    )

    assert paths.root == tmp_path / "garmin"
