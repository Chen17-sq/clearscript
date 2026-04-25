"""Anthropic Claude provider."""

from __future__ import annotations

from collections.abc import Iterator

from clearscript.providers.base import ChatMessage, ChatResponse, _BaseProvider, time_ms


class AnthropicProvider(_BaseProvider):
    name = "anthropic"

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        from anthropic import Anthropic

        kwargs: dict[str, object] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = Anthropic(**kwargs)  # type: ignore[arg-type]

    def chat(self, messages: list[ChatMessage], model: str, **kwargs: object) -> ChatResponse:
        system_parts = [m.content for m in messages if m.role == "system"]
        anthropic_messages = [
            {"role": m.role, "content": m.content} for m in messages if m.role != "system"
        ]
        max_tokens = int(kwargs.get("max_tokens", 8192))  # type: ignore[arg-type]
        temperature = float(kwargs.get("temperature", 0.0))  # type: ignore[arg-type]

        start = time_ms()
        result = self._client.messages.create(  # type: ignore[call-arg]
            model=model,
            system="\n\n".join(system_parts) if system_parts else None,  # type: ignore[arg-type]
            messages=anthropic_messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=temperature,
        )
        latency = time_ms() - start

        text = "".join(
            block.text  # type: ignore[union-attr]
            for block in result.content
            if getattr(block, "type", None) == "text"
        )

        return ChatResponse(
            text=text,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            model=model,
            provider=self.name,
            latency_ms=latency,
            raw=result,
        )

    def stream(self, messages: list[ChatMessage], model: str, **kwargs: object) -> Iterator[str]:
        system_parts = [m.content for m in messages if m.role == "system"]
        anthropic_messages = [
            {"role": m.role, "content": m.content} for m in messages if m.role != "system"
        ]
        max_tokens = int(kwargs.get("max_tokens", 8192))  # type: ignore[arg-type]
        temperature = float(kwargs.get("temperature", 0.0))  # type: ignore[arg-type]

        with self._client.messages.stream(  # type: ignore[call-arg]
            model=model,
            system="\n\n".join(system_parts) if system_parts else None,  # type: ignore[arg-type]
            messages=anthropic_messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=temperature,
        ) as stream:
            yield from stream.text_stream
