"""One-time, local-only Garmin Connect authentication."""

import os
import stat
from collections.abc import Callable
from getpass import getpass
from pathlib import Path
from typing import Protocol, cast

from garminconnect import Garmin

from .security import reject_symlink_ancestors, require_private_directory


class LoginClient(Protocol):
    def login(self, tokenstore: str) -> tuple[str | None, str | None]: ...


ClientFactory = Callable[[str, str, Callable[[], str]], LoginClient]


def _garmin_factory(
    email: str, password: str, prompt_mfa: Callable[[], str]
) -> LoginClient:
    return cast(LoginClient, Garmin(email=email, password=password, prompt_mfa=prompt_mfa))


def _prepare_private_directory(path: Path) -> None:
    reject_symlink_ancestors(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    require_private_directory(path.parent)
    if path.exists():
        require_private_directory(path)
    else:
        path.mkdir(mode=0o700)


def _validate_token_files(path: Path, *, protect: bool = False) -> None:
    for entry in path.iterdir():
        if entry.is_symlink():
            raise ValueError("token directory must not contain symbolic links")
        metadata = entry.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("token entries must be regular files")
        if metadata.st_uid != os.getuid():
            raise ValueError("token material must be owner-only")
        if protect:
            os.chmod(entry, 0o600)
        elif metadata.st_mode & 0o077:
            raise ValueError("token material must be owner-only")


def authenticate(
    token_dir: Path,
    *,
    client_factory: ClientFactory = _garmin_factory,
    email_input: Callable[[str], str] = input,
    secret_input: Callable[[str], str] = getpass,
) -> None:
    """Authenticate interactively and save only reusable session material."""
    _prepare_private_directory(token_dir)
    _validate_token_files(token_dir)
    email = email_input("Garmin email: ").strip()
    if not email:
        raise ValueError("Garmin email is required")
    password = secret_input("Garmin password: ")
    if not password:
        raise ValueError("Garmin password is required")
    client = client_factory(email, password, lambda: secret_input("Garmin MFA code: "))
    client.login(str(token_dir))
    _validate_token_files(token_dir, protect=True)
    required_tokens = {"garmin_tokens.json"}
    if not required_tokens.issubset(entry.name for entry in token_dir.iterdir()):
        raise ValueError("authentication did not create reusable token material")
