"""OpenAI and OpenAI-compatible providers (DeepSeek, Moonshot, Together, Groq, etc.)."""

from __future__ import annotations

from collections.abc import Iterator

from clearscript.providers.base import ChatMessage, ChatResponse, _BaseProvider, time_ms


class OpenAICompatProvider(_BaseProvider):
    """Single adapter for native OpenAI and OpenAI-compatible endpoints.

    Configure via ``base_url`` to point at any compatible service: DeepSeek,
    Moonshot/Kimi, Qwen API, Together, Groq, Fireworks, Mistral, OpenRouter,
    Perplexity, Zhipu, MiniMax, StepFun, 01.AI, Cohere, SambaNova, etc.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        provider_name: str = "openai-compat",
    ) -> None:
        from openai import OpenAI

        kwargs: dict[str, object] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)  # type: ignore[arg-type]
        self.name = provider_name

    def chat(self, messages: list[ChatMessage], model: str, **kwargs: object) -> ChatResponse:
        oai_messages = [{"role": m.role, "content": m.content} for m in messages]
        max_tokens = kwargs.get("max_tokens")
        temperature = float(kwargs.get("temperature", 0.0))  # type: ignore[arg-type]

        call_kwargs: dict[str, object] = {
            "model": model,
            "messages": oai_messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            call_kwargs["max_tokens"] = int(max_tokens)  # type: ignore[arg-type]

        start = time_ms()
        result = self._client.chat.completions.create(**call_kwargs)  # type: ignore[arg-type]
        latency = time_ms() - start

        text = result.choices[0].message.content or ""
        usage = result.usage
        return ChatResponse(
            text=text,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=model,
            provider=self.name,
            latency_ms=latency,
            raw=result,
        )

    def stream(self, messages: list[ChatMessage], model: str, **kwargs: object) -> Iterator[str]:
        oai_messages = [{"role": m.role, "content": m.content} for m in messages]
        max_tokens = kwargs.get("max_tokens")
        temperature = float(kwargs.get("temperature", 0.0))  # type: ignore[arg-type]

        call_kwargs: dict[str, object] = {
            "model": model,
            "messages": oai_messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            call_kwargs["max_tokens"] = int(max_tokens)  # type: ignore[arg-type]

        for chunk in self._client.chat.completions.create(**call_kwargs):  # type: ignore[arg-type]
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
