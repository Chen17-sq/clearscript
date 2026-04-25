"""Google Gemini provider."""

from __future__ import annotations

from collections.abc import Iterator

from clearscript.providers.base import ChatMessage, ChatResponse, _BaseProvider, time_ms


class GoogleProvider(_BaseProvider):
    name = "google"

    def __init__(self, api_key: str) -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._genai = genai

    def _build_history(
        self, messages: list[ChatMessage]
    ) -> tuple[str | None, list[dict[str, object]]]:
        system_parts = [m.content for m in messages if m.role == "system"]
        history = []
        for m in messages:
            if m.role == "system":
                continue
            role = "user" if m.role == "user" else "model"
            history.append({"role": role, "parts": [m.content]})
        return ("\n\n".join(system_parts) if system_parts else None, history)

    def chat(self, messages: list[ChatMessage], model: str, **kwargs: object) -> ChatResponse:
        system, history = self._build_history(messages)
        gen_model = self._genai.GenerativeModel(model_name=model, system_instruction=system)
        temperature = float(kwargs.get("temperature", 0.0))  # type: ignore[arg-type]
        max_tokens = kwargs.get("max_output_tokens", 8192)

        start = time_ms()
        result = gen_model.generate_content(
            history,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": int(max_tokens),  # type: ignore[arg-type]
            },
        )
        latency = time_ms() - start

        text = result.text or ""
        usage = getattr(result, "usage_metadata", None)
        in_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        out_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
        return ChatResponse(
            text=text,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            model=model,
            provider=self.name,
            latency_ms=latency,
            raw=result,
        )

    def stream(self, messages: list[ChatMessage], model: str, **kwargs: object) -> Iterator[str]:
        system, history = self._build_history(messages)
        gen_model = self._genai.GenerativeModel(model_name=model, system_instruction=system)
        temperature = float(kwargs.get("temperature", 0.0))  # type: ignore[arg-type]
        max_tokens = kwargs.get("max_output_tokens", 8192)

        stream_iter = gen_model.generate_content(
            history,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": int(max_tokens),  # type: ignore[arg-type]
            },
            stream=True,
        )
        for chunk in stream_iter:
            if chunk.text:
                yield chunk.text
