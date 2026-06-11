"""Shared pytest fixtures."""

from __future__ import annotations

from typing import ClassVar

import pytest

from clearscript.providers.base import ChatMessage, ChatResponse


class MockProvider:
    """Deterministic LLM provider for tests."""

    name = "mock"

    def __init__(self, response_text: str = "Mock response") -> None:
        self.response_text = response_text
        self.calls: list[list[ChatMessage]] = []

    def chat(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(list(messages))
        return ChatResponse(
            text=self.response_text,
            input_tokens=100,
            output_tokens=50,
            model=model,
            provider=self.name,
            latency_ms=1.0,
        )

    def stream(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        yield self.response_text

    def chat_with_progress(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        """Test stub: yield the canned response as a single delta, then a 'done' event."""
        self.calls.append(list(messages))
        yield ("delta", self.response_text)
        yield (
            "done",
            ChatResponse(
                text=self.response_text,
                input_tokens=100,
                output_tokens=50,
                model=model,
                provider=self.name,
                latency_ms=1.0,
            ),
        )


@pytest.fixture
def mock_provider() -> MockProvider:
    return MockProvider()


@pytest.fixture
def tmp_library(tmp_path):  # type: ignore[no-untyped-def]
    from clearscript.library import Library

    lib = Library(tmp_path / "library.db")
    yield lib
    lib.close()


@pytest.fixture(autouse=True)
def _hermetic_environment(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """Keep the suite hermetic on developer machines.

    1. Prompt overrides: a real ``~/.config/clearscript/prompts/`` on the
       dev's machine would silently replace the bundled prompts under test.
       Point the override dir at an empty tmp dir.
    2. OS keyring: /api/providers and resolve_api_key probe the real
       keychain — slow, non-deterministic, and can pop interactive prompts
       on macOS. Substitute an in-memory fake for every test.
    """
    monkeypatch.setattr(
        "clearscript.prompts._USER_OVERRIDE_DIR", tmp_path / "prompt-overrides"
    )

    class _FakeKeyringErrors:
        class PasswordDeleteError(Exception):
            pass

    class _FakeKeyring:
        errors = _FakeKeyringErrors
        _store: ClassVar[dict[tuple[str, str], str]] = {}

        @classmethod
        def get_password(cls, service, account):  # type: ignore[no-untyped-def]
            return cls._store.get((service, account))

        @classmethod
        def set_password(cls, service, account, password):  # type: ignore[no-untyped-def]
            cls._store[(service, account)] = password

        @classmethod
        def delete_password(cls, service, account):  # type: ignore[no-untyped-def]
            if (service, account) not in cls._store:
                raise _FakeKeyringErrors.PasswordDeleteError("not found")
            del cls._store[(service, account)]

    _FakeKeyring._store = {}
    import sys

    monkeypatch.setitem(sys.modules, "keyring", _FakeKeyring)
