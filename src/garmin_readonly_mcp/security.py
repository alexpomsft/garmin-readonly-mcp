"""Filesystem checks for owner-private local state."""

import os
import stat
from pathlib import Path


def reject_symlink_ancestors(path: Path) -> None:
    """Reject any existing symbolic link in a path or its ancestors."""
    current = path.expanduser()
    for candidate in (current, *current.parents):
        if candidate.is_symlink():
            raise ValueError("state path must not contain a symbolic link")


def require_private_directory(path: Path) -> None:
    """Require an owner-controlled, owner-only real directory."""
    reject_symlink_ancestors(path)
    metadata = path.stat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_mode & 0o077
    ):
        raise ValueError("state directory must be an owner-only real directory")
