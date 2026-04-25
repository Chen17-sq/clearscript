"""LLM provider abstraction.

All adapters implement the ``LLMProvider`` protocol. The pipeline is written
against this protocol, so swapping providers is config-only.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    role: Role
    content: str


@dataclass
class ChatResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str
    latency_ms: float
    raw: object = field(default=None, repr=False)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMProvider(Protocol):
    """Common interface implemented by every provider adapter."""

    name: str

    def chat(self, messages: list[ChatMessage], model: str, **kwargs: object) -> ChatResponse:
        """Send messages, return the response."""
        ...

    def stream(self, messages: list[ChatMessage], model: str, **kwargs: object) -> Iterator[str]:
        """Stream response chunks (text deltas)."""
        ...


class _BaseProvider:
    """Helper base for adapters that want a default ``stream`` impl built on ``chat``."""

    name: str = "base"

    def stream(self, messages: list[ChatMessage], model: str, **kwargs: object) -> Iterator[str]:
        response = self.chat(messages, model, **kwargs)  # type: ignore[attr-defined]
        yield response.text


def time_ms() -> float:
    return time.perf_counter() * 1000.0
