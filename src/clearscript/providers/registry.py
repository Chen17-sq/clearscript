"""Build the right provider instance from a ProviderConfig."""

from __future__ import annotations

from clearscript.config import ProviderConfig
from clearscript.providers.base import LLMProvider


def build_provider(config: ProviderConfig) -> LLMProvider:
    """Instantiate the provider matching the config's ``type``."""
    provider_type = config.type.lower()

    if provider_type == "anthropic":
        from clearscript.providers.anthropic import AnthropicProvider

        api_key = config.resolve_api_key()
        if not api_key:
            raise RuntimeError(
                f"No API key for Anthropic provider {config.name!r}. "
                f"Set {config.api_key_env} or provide api_key in providers.toml."
            )
        return AnthropicProvider(api_key=api_key, base_url=config.base_url)

    if provider_type in {"openai", "openai-compat", "openai_compat"}:
        from clearscript.providers.openai_compat import OpenAICompatProvider

        api_key = config.resolve_api_key() or "no-auth-required"
        return OpenAICompatProvider(
            api_key=api_key,
            base_url=config.base_url,
            provider_name=config.name,
        )

    if provider_type == "google":
        from clearscript.providers.google import GoogleProvider

        api_key = config.resolve_api_key()
        if not api_key:
            raise RuntimeError(
                f"No API key for Google provider {config.name!r}. "
                f"Set {config.api_key_env} or provide api_key in providers.toml."
            )
        return GoogleProvider(api_key=api_key)

    if provider_type == "ollama":
        from clearscript.providers.ollama import OllamaProvider

        return OllamaProvider(base_url=config.base_url or "http://localhost:11434")

    if provider_type == "custom":
        from clearscript.providers.openai_compat import OpenAICompatProvider

        api_key = config.resolve_api_key() or "no-auth-required"
        return OpenAICompatProvider(
            api_key=api_key,
            base_url=config.base_url,
            provider_name=config.name,
        )

    raise ValueError(
        f"Unknown provider type {provider_type!r}. "
        "Supported: anthropic, openai, openai-compat, google, ollama, custom."
    )
