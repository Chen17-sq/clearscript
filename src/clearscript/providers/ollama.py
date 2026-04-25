"""Ollama provider for local models. Talks the native Ollama HTTP API."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from clearscript.providers.base import ChatMessage, ChatResponse, _BaseProvider, time_ms


class OllamaProvider(_BaseProvider):
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=600.0)

    def chat(self, messages: list[ChatMessage], model: str, **kwargs: object) -> ChatResponse:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": float(kwargs.get("temperature", 0.0)),  # type: ignore[arg-type]
                "num_predict": int(kwargs.get("max_tokens", 8192)),  # type: ignore[arg-type]
            },
        }
        start = time_ms()
        response = self._client.post(f"{self._base_url}/api/chat", json=payload)
        response.raise_for_status()
        latency = time_ms() - start
        data = response.json()

        return ChatResponse(
            text=data["message"]["content"],
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            model=model,
            provider=self.name,
            latency_ms=latency,
            raw=data,
        )

    def stream(self, messages: list[ChatMessage], model: str, **kwargs: object) -> Iterator[str]:
        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {
                "temperature": float(kwargs.get("temperature", 0.0)),  # type: ignore[arg-type]
                "num_predict": int(kwargs.get("max_tokens", 8192)),  # type: ignore[arg-type]
            },
        }
        with self._client.stream("POST", f"{self._base_url}/api/chat", json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                event = json.loads(line)
                content = event.get("message", {}).get("content", "")
                if content:
                    yield content
                if event.get("done"):
                    break
