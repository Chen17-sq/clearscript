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

    def chat_with_progress(
        self, messages: list[ChatMessage], model: str, **kwargs: object
    ) -> Iterator[tuple[str, object]]:
        """Stream ``("delta", str)`` events, then a single ``("done", ChatResponse)``.

        The pipeline drives chunks through this method so the UI can show
        text appearing live. The terminal ``done`` event carries real usage
        counts when the SDK provides them; ``_BaseProvider`` falls back to
        an estimate.
        """
        ...


class _BaseProvider:
    """Helper base for adapters that want a default ``stream`` impl built on ``chat``."""

    name: str = "base"

    def stream(self, messages: list[ChatMessage], model: str, **kwargs: object) -> Iterator[str]:
        response = self.chat(messages, model, **kwargs)  # type: ignore[attr-defined]
        yield response.text

    def chat_with_progress(
        self, messages: list[ChatMessage], model: str, **kwargs: object
    ) -> Iterator[tuple[str, object]]:
        """Default implementation: stream deltas, then emit a synthetic ('done', ChatResponse).

        Subclasses that have access to streaming usage info should override
        this to capture real input/output token counts from the underlying SDK.
        For adapters that fall through to this default, output_tokens are
        estimated from the response character count.
        """
        accumulated = ""
        start = time_ms()
        for delta in self.stream(messages, model, **kwargs):  # type: ignore[attr-defined]
            accumulated += delta
            yield ("delta", delta)
        latency = time_ms() - start
        # Estimate token counts when SDK didn't provide usage
        from clearscript.core.chunking import estimate_tokens

        input_text = "\n".join(m.content for m in messages)
        response = ChatResponse(
            text=accumulated,
            input_tokens=estimate_tokens(input_text),
            output_tokens=estimate_tokens(accumulated),
            model=model,
            provider=getattr(self, "name", "unknown"),
            latency_ms=latency,
        )
        yield ("done", response)


def time_ms() -> float:
    return time.perf_counter() * 1000.0
