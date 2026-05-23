"""Tests for the real-SDK provider adapters.

These don't hit the network — they patch the SDK client's underlying
methods (``messages.create`` / ``chat.completions.create``) with mocks
that return canned response/stream objects, then verify that the
provider correctly translates SDK calls into ``ChatResponse`` /
streaming-event tuples.

Without these, the provider adapters were only smoke-tested through
``_BaseProvider`` fallbacks. A regression in SDK call shape (renamed
field, changed kwarg) would slip past CI until someone runs against a
real API and gets an error.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from clearscript.providers.base import ChatMessage

# ============ Anthropic ============


@pytest.fixture
def anthropic_provider(monkeypatch):
    """Build an AnthropicProvider whose .messages.create / .stream are mocks."""
    from clearscript.providers.anthropic import AnthropicProvider

    # Replace the underlying Anthropic() constructor with a MagicMock so
    # we never reach the real SDK.
    class FakeAnthropic:
        def __init__(self, **kwargs) -> None:
            self.messages = MagicMock()

    monkeypatch.setattr("anthropic.Anthropic", FakeAnthropic)

    return AnthropicProvider(api_key="test-key")


def test_anthropic_chat_translates_sdk_response(anthropic_provider) -> None:
    """A successful messages.create returns a ChatResponse with real usage."""
    # Build a fake SDK response: content is a list of text blocks, usage
    # has input_tokens + output_tokens.
    fake_block = SimpleNamespace(type="text", text="Cleaned transcript here.")
    fake_usage = SimpleNamespace(input_tokens=123, output_tokens=45)
    fake_response = SimpleNamespace(content=[fake_block], usage=fake_usage)
    anthropic_provider._client.messages.create.return_value = fake_response

    result = anthropic_provider.chat(
        [
            ChatMessage(role="system", content="be terse"),
            ChatMessage(role="user", content="hi"),
        ],
        model="claude-opus-4-7",
    )
    assert result.text == "Cleaned transcript here."
    assert result.input_tokens == 123
    assert result.output_tokens == 45
    assert result.model == "claude-opus-4-7"
    assert result.provider == "anthropic"

    # The SDK was called with the right kwargs.
    call_kwargs = anthropic_provider._client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-7"
    assert call_kwargs["system"] == "be terse"  # system extracted out
    assert call_kwargs["messages"] == [{"role": "user", "content": "hi"}]
    assert call_kwargs["max_tokens"] == 8192  # default


def test_anthropic_chat_concatenates_multiple_system_messages(anthropic_provider) -> None:
    """Multiple system messages get joined with \\n\\n before being sent."""
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="ok")],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    anthropic_provider._client.messages.create.return_value = fake_response

    anthropic_provider.chat(
        [
            ChatMessage(role="system", content="part 1"),
            ChatMessage(role="system", content="part 2"),
            ChatMessage(role="user", content="hi"),
        ],
        model="claude-opus-4-7",
    )
    sent_system = anthropic_provider._client.messages.create.call_args.kwargs[
        "system"
    ]
    assert sent_system == "part 1\n\npart 2"


def test_anthropic_chat_ignores_non_text_content_blocks(anthropic_provider) -> None:
    """Tool-use / image blocks must not crash the text extractor."""
    fake_response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="first "),
            SimpleNamespace(type="tool_use", input={"x": 1}),  # no .text
            SimpleNamespace(type="text", text="second"),
        ],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    anthropic_provider._client.messages.create.return_value = fake_response

    result = anthropic_provider.chat(
        [ChatMessage(role="user", content="hi")],
        model="claude-opus-4-7",
    )
    assert result.text == "first second"


def test_anthropic_chat_with_progress_emits_deltas_then_done(
    anthropic_provider,
) -> None:
    """chat_with_progress streams via messages.stream() — verify the
    (delta, str)+ / (done, ChatResponse) protocol.

    The Anthropic SDK exposes ``messages.stream(...)`` as a context
    manager that yields a stream object. We mock that and inject our
    own ``text_stream`` iterable + ``get_final_message`` result.
    """
    fake_final = SimpleNamespace(
        usage=SimpleNamespace(input_tokens=200, output_tokens=80),
    )

    class FakeStream:
        def __init__(self) -> None:
            self.text_stream = ["Hello ", "world", "!"]

        def get_final_message(self):  # type: ignore[no-untyped-def]
            return fake_final

    class StreamCtx:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return FakeStream()

        def __exit__(self, *a, **k):  # type: ignore[no-untyped-def]
            return False

    anthropic_provider._client.messages.stream.return_value = StreamCtx()

    events = list(
        anthropic_provider.chat_with_progress(
            [ChatMessage(role="user", content="hi")],
            model="claude-opus-4-7",
        )
    )
    kinds = [k for k, _ in events]
    assert kinds == ["delta", "delta", "delta", "done"]
    deltas = [p for k, p in events if k == "delta"]
    assert deltas == ["Hello ", "world", "!"]

    done_kind, done_payload = events[-1]
    assert done_kind == "done"
    assert done_payload.text == "Hello world!"
    assert done_payload.input_tokens == 200
    assert done_payload.output_tokens == 80


# ============ OpenAI-compat ============


@pytest.fixture
def openai_compat_provider(monkeypatch):
    """Build an OpenAICompatProvider whose .chat.completions.create is a mock."""
    from clearscript.providers.openai_compat import OpenAICompatProvider

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            self.chat = SimpleNamespace(completions=MagicMock())

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    return OpenAICompatProvider(
        api_key="test-key",
        base_url="https://api.deepseek.com/v1",
        provider_name="deepseek",
    )


def test_openai_compat_chat_returns_response(openai_compat_provider) -> None:
    """A non-streaming chat returns a ChatResponse with usage from the SDK."""
    fake_message = SimpleNamespace(content="Cleaned text.")
    fake_choice = SimpleNamespace(message=fake_message)
    fake_usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
    fake_response = SimpleNamespace(choices=[fake_choice], usage=fake_usage)
    openai_compat_provider._client.chat.completions.create.return_value = fake_response

    result = openai_compat_provider.chat(
        [ChatMessage(role="user", content="hi")],
        model="deepseek-v4-flash",
    )
    assert result.text == "Cleaned text."
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.provider == "deepseek"


def test_openai_compat_chat_with_progress_streams_and_captures_usage(
    openai_compat_provider,
) -> None:
    """chat_with_progress yields deltas and captures usage from the final chunk.

    The OpenAI SDK with ``stream=True`` + ``stream_options={include_usage: True}``
    yields a sequence where intermediate chunks have ``choices[0].delta.content``
    and the *final* chunk has empty choices but populated ``.usage``.
    """
    # Intermediate chunks: each has one choice with a delta.content
    def make_chunk(text):  # type: ignore[no-untyped-def]
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=text))],
            usage=None,
        )

    final_chunk = SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(prompt_tokens=42, completion_tokens=17),
    )
    openai_compat_provider._client.chat.completions.create.return_value = iter(
        [
            make_chunk("Hello "),
            make_chunk("world"),
            make_chunk("."),
            final_chunk,
        ]
    )

    events = list(
        openai_compat_provider.chat_with_progress(
            [ChatMessage(role="user", content="hi")],
            model="deepseek-v4-flash",
        )
    )
    kinds = [k for k, _ in events]
    assert kinds == ["delta", "delta", "delta", "done"]
    deltas = [p for k, p in events if k == "delta"]
    assert deltas == ["Hello ", "world", "."]

    _, payload = events[-1]
    assert payload.text == "Hello world."
    assert payload.input_tokens == 42
    assert payload.output_tokens == 17

    # Verify the SDK was invoked with stream_options requesting usage.
    call_kwargs = (
        openai_compat_provider._client.chat.completions.create.call_args.kwargs
    )
    assert call_kwargs["stream"] is True
    assert call_kwargs["stream_options"] == {"include_usage": True}


def test_openai_compat_chat_with_progress_falls_back_when_usage_missing(
    openai_compat_provider,
) -> None:
    """If the provider doesn't honor include_usage, we still emit done with
    estimated token counts so the UI has something to display.
    """
    def make_chunk(text):  # type: ignore[no-untyped-def]
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=text))],
            usage=None,
        )

    openai_compat_provider._client.chat.completions.create.return_value = iter(
        [make_chunk("partial"), make_chunk(" output")]
    )

    events = list(
        openai_compat_provider.chat_with_progress(
            [ChatMessage(role="user", content="hi")],
            model="deepseek-v4-flash",
        )
    )
    _, payload = events[-1]
    assert payload.text == "partial output"
    # Estimated, but non-zero.
    assert payload.input_tokens > 0
    assert payload.output_tokens > 0
