"""Tests for clearscript.config — provider resolution + env handling."""

from __future__ import annotations

from clearscript.config import ProviderConfig


def test_resolve_api_key_returns_inline_value() -> None:
    p = ProviderConfig(name="claude", type="anthropic", api_key="sk-inline")
    assert p.resolve_api_key() == "sk-inline"


def test_resolve_api_key_returns_env_value(monkeypatch) -> None:
    monkeypatch.setenv("MY_TEST_KEY", "sk-env")
    p = ProviderConfig(
        name="test",
        type="anthropic",
        api_key_env="MY_TEST_KEY",
    )
    assert p.resolve_api_key() == "sk-env"


def test_resolve_api_key_returns_none_when_env_var_is_empty_string(
    monkeypatch,
) -> None:
    """The actual user-visible bug behind v0.0.16:

    ``ANTHROPIC_API_KEY=`` in someone's shell (declared but blank) used
    to return ``""`` and bubble up as ``has_key=True`` in the UI,
    enabling the provider pill — which would then fail at request time
    with an authentication error.
    """
    monkeypatch.setenv("MY_BLANK_KEY", "")
    p = ProviderConfig(
        name="test",
        type="anthropic",
        api_key_env="MY_BLANK_KEY",
    )
    assert p.resolve_api_key() is None


def test_resolve_api_key_returns_none_when_env_var_is_whitespace(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MY_WS_KEY", "   ")
    p = ProviderConfig(
        name="test",
        type="anthropic",
        api_key_env="MY_WS_KEY",
    )
    assert p.resolve_api_key() is None


def test_resolve_api_key_returns_none_when_inline_is_whitespace() -> None:
    p = ProviderConfig(name="test", type="anthropic", api_key="   ")
    assert p.resolve_api_key() is None


def test_resolve_api_key_returns_none_when_no_source_configured() -> None:
    p = ProviderConfig(name="test", type="anthropic")
    assert p.resolve_api_key() is None


def test_resolve_api_key_keyring_wins_over_env(monkeypatch) -> None:
    """If both keyring AND env var have a key, keyring should win — that's
    how the in-app input takes priority over a stale shell export.
    """
    import sys

    monkeypatch.setenv("MY_ENV_KEY", "sk-from-env")

    class FakeKeyring:
        @staticmethod
        def get_password(service, account):  # type: ignore[no-untyped-def]
            return "sk-from-keyring"

    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring)

    p = ProviderConfig(
        name="claude",
        type="anthropic",
        api_key_env="MY_ENV_KEY",
    )
    assert p.resolve_api_key() == "sk-from-keyring"


def test_resolve_api_key_keyring_failure_falls_through_to_env(
    monkeypatch,
) -> None:
    """A flaky keyring backend (e.g. headless Linux without DBus) must
    NOT prevent env var resolution.
    """
    import sys

    monkeypatch.setenv("MY_ENV_KEY", "sk-env-fallback")

    class BrokenKeyring:
        @staticmethod
        def get_password(service, account):  # type: ignore[no-untyped-def]
            raise RuntimeError("no DBus session available")

    monkeypatch.setitem(sys.modules, "keyring", BrokenKeyring)

    p = ProviderConfig(
        name="test",
        type="anthropic",
        api_key_env="MY_ENV_KEY",
    )
    assert p.resolve_api_key() == "sk-env-fallback"


def test_resolve_api_key_inline_wins_over_keyring(monkeypatch) -> None:
    """TOML config takes ultimate priority — that's the contract for
    teams that share a providers.toml file.
    """
    import sys

    class FakeKeyring:
        @staticmethod
        def get_password(service, account):  # type: ignore[no-untyped-def]
            return "sk-keyring"

    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring)

    p = ProviderConfig(
        name="test",
        type="anthropic",
        api_key="sk-inline",
    )
    assert p.resolve_api_key() == "sk-inline"
