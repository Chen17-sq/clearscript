"""Shared pytest fixtures."""

from __future__ import annotations

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


@pytest.fixture
def mock_provider() -> MockProvider:
    return MockProvider()


@pytest.fixture
def tmp_library(tmp_path):  # type: ignore[no-untyped-def]
    from clearscript.library import Library

    lib = Library(tmp_path / "library.db")
    yield lib
    lib.close()
