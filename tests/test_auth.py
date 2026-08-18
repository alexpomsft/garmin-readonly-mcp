import os
from pathlib import Path
from typing import Any

import pytest

from garmin_readonly_mcp.auth import authenticate


class FakeClient:
    def __init__(self, email: str, password: str, prompt_mfa: Any) -> None:
        self.email = email
        self.password = password
        self.prompt_mfa = prompt_mfa
        self.login_path: str | None = None

    def login(self, tokenstore: str) -> tuple[None, None]:
        self.login_path = tokenstore
        Path(tokenstore, "garmin_tokens.json").write_text("{}", encoding="utf-8")
        return None, None


def test_authenticate_uses_hidden_local_inputs_and_protects_tokens(tmp_path: Path) -> None:
    created: list[FakeClient] = []
    prompts: list[str] = []

    def factory(email: str, password: str, prompt_mfa: Any) -> FakeClient:
        client = FakeClient(email, password, prompt_mfa)
        created.append(client)
        return client

    def secret_input(prompt: str) -> str:
        prompts.append(prompt)
        return "mfa-code" if "MFA" in prompt else "local-password"

    token_dir = tmp_path / "tokens"
    authenticate(
        token_dir,
        client_factory=factory,
        email_input=lambda _: "alex@example.com",
        secret_input=secret_input,
    )

    assert created[0].email == "alex@example.com"
    assert created[0].password == "local-password"
    assert created[0].prompt_mfa() == "mfa-code"
    assert created[0].login_path == str(token_dir)
    assert token_dir.stat().st_mode & 0o777 == 0o700
    assert (token_dir / "garmin_tokens.json").stat().st_mode & 0o777 == 0o600
    assert prompts == ["Garmin password: ", "Garmin MFA code: "]


def test_authenticate_rejects_preexisting_symlinks_before_login(tmp_path: Path) -> None:
    token_dir = tmp_path / "tokens"
    token_dir.mkdir(mode=0o700)
    (token_dir / "oauth1_token.json").symlink_to(tmp_path / "outside")
    factory_called = False

    def factory(email: str, password: str, prompt_mfa: Any) -> FakeClient:
        nonlocal factory_called
        factory_called = True
        raise AssertionError("factory must not be called")

    with pytest.raises(ValueError, match="symbolic links"):
        authenticate(
            token_dir,
            client_factory=factory,
            email_input=lambda _: "alex@example.com",
            secret_input=lambda _: "not-used",
        )

    assert factory_called is False


def test_authenticate_rejects_symlinked_token_ancestor(tmp_path: Path) -> None:
    real_state = tmp_path / "real-state"
    real_state.mkdir(mode=0o700)
    linked_state = tmp_path / "linked-state"
    linked_state.symlink_to(real_state, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic link"):
        authenticate(
            linked_state / "tokens",
            client_factory=lambda *args: pytest.fail("factory must not be called"),
            email_input=lambda _: "alex@example.com",
            secret_input=lambda _: "not-used",
        )


def test_authenticate_rejects_nonprivate_state_directory(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o755)

    with pytest.raises(ValueError, match="owner-only"):
        authenticate(
            state / "tokens",
            client_factory=lambda *args: pytest.fail("factory must not be called"),
            email_input=lambda _: "alex@example.com",
            secret_input=lambda _: "not-used",
        )


def test_authenticate_rejects_preexisting_special_token_entry(tmp_path: Path) -> None:
    token_dir = tmp_path / "tokens"
    token_dir.mkdir(mode=0o700)
    os.mkfifo(token_dir / "oauth1_token.json", mode=0o600)

    with pytest.raises(ValueError, match="regular files"):
        authenticate(
            token_dir,
            client_factory=lambda *args: pytest.fail("factory must not be called"),
            email_input=lambda _: "alex@example.com",
            secret_input=lambda _: "not-used",
        )


def test_authenticate_requires_reusable_token_material_after_login(tmp_path: Path) -> None:
    class EmptyClient:
        def login(self, tokenstore: str) -> tuple[None, None]:
            return None, None

    with pytest.raises(ValueError, match="reusable token material"):
        authenticate(
            tmp_path / "tokens",
            client_factory=lambda *args: EmptyClient(),
            email_input=lambda _: "alex@example.com",
            secret_input=lambda _: "password",
        )
