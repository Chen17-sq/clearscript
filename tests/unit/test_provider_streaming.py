"""Tests for the streaming provider contract.

Covers ``_BaseProvider.chat_with_progress`` (the default fallback) and the
LLMProvider Protocol shape. The real SDK-backed providers
(``AnthropicProvider``, ``OpenAICompatProvider``) are exercised through
the server integration tests with mocks — testing the actual SDK calls
would require live network access.
"""

from __future__ import annotations

from collections.abc import Iterator

from clearscript.providers.base import ChatMessage, ChatResponse, _BaseProvider


class StreamingBase(_BaseProvider):
    """A minimal subclass of _BaseProvider that yields the canned response.

    Used to verify _BaseProvider's default ``chat_with_progress`` correctly
    wraps a regular ``stream()`` implementation into the (delta, done)
    event protocol.
    """

    name = "streaming-base"

    def __init__(self, response_text: str, *, chunks: int = 3) -> None:
        self.response_text = response_text
        self.chunks = chunks

    def chat(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        return ChatResponse(
            text=self.response_text,
            input_tokens=100,
            output_tokens=50,
            model=model,
            provider=self.name,
            latency_ms=1.0,
        )

    def stream(self, messages, model, **kwargs):  # type: ignore[no-untyped-def, override]
        # Split into N pieces so the default chat_with_progress has
        # multiple deltas to forward.
        slice_len = max(1, len(self.response_text) // self.chunks)
        for i in range(0, len(self.response_text), slice_len):
            yield self.response_text[i : i + slice_len]


def _messages(text: str = "hi") -> list[ChatMessage]:
    return [ChatMessage(role="user", content=text)]


def test_default_chat_with_progress_emits_delta_then_done() -> None:
    """The base impl wraps stream() into (delta, payload)+ then (done, ChatResponse)."""
    provider = StreamingBase("Hello world from the stream", chunks=4)
    events = list(provider.chat_with_progress(_messages(), "mock-model"))

    kinds = [k for k, _ in events]
    assert kinds[-1] == "done", "must end with done"
    assert all(k == "delta" for k in kinds[:-1]), "all but last must be deltas"
    assert kinds.count("delta") >= 2


def test_default_chat_with_progress_done_payload_is_chat_response() -> None:
    provider = StreamingBase("payload check", chunks=2)
    events = list(provider.chat_with_progress(_messages(), "mock-model"))
    kind, payload = events[-1]
    assert kind == "done"
    assert isinstance(payload, ChatResponse)
    # The accumulated text in the done payload matches what was yielded.
    accumulated = "".join(str(p) for k, p in events[:-1] if k == "delta")
    assert accumulated == "payload check"
    assert payload.text == "payload check"


def test_default_chat_with_progress_token_estimates_present() -> None:
    """When the underlying stream has no usage info, base estimates tokens
    from the text length so the UI always has SOMETHING to display.
    """
    provider = StreamingBase("X" * 4000, chunks=4)  # ~1000 tokens
    events = list(provider.chat_with_progress(_messages(), "mock-model"))
    _, response = events[-1]
    assert response.input_tokens > 0
    assert response.output_tokens > 0
    # Sanity: 4000 chars / ~4 per token ≈ 1000.
    assert 500 < response.output_tokens < 2000


def test_default_chat_with_progress_handles_empty_stream() -> None:
    """A provider whose stream yields nothing still emits a 'done' event."""

    class EmptyStream(_BaseProvider):
        name = "empty"

        def chat(self, *a, **k):  # type: ignore[no-untyped-def]
            return ChatResponse(
                text="",
                input_tokens=0,
                output_tokens=0,
                model="m",
                provider="empty",
                latency_ms=1.0,
            )

        def stream(self, *a, **k) -> Iterator[str]:  # type: ignore[no-untyped-def]
            return iter([])

    events = list(EmptyStream().chat_with_progress(_messages(), "m"))
    assert events[-1][0] == "done"
    assert events[-1][1].text == ""


def test_chat_response_total_tokens_property() -> None:
    """ChatResponse.total_tokens sums input+output — used by cost display."""
    r = ChatResponse(
        text="abc",
        input_tokens=100,
        output_tokens=50,
        model="x",
        provider="y",
        latency_ms=1.0,
    )
    assert r.total_tokens == 150
