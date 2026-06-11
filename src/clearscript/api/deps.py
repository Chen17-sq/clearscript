"""Shared application state and dependency helpers for the API routers.

``AppState`` replaces the closure-captured ``cfg_holder`` / ``seed_installed``
dicts from the pre-refactor monolithic ``server.py``. One instance is created
per ``create_app()`` call and passed to each router factory, preserving the
original lazy-config + once-per-boot seed-pack semantics.

``build_provider`` is imported at module level on purpose: tests monkeypatch
``clearscript.api.deps.build_provider`` to inject stub LLM providers, and the
code below calls the bare module-global name so the patch takes effect.
"""

from __future__ import annotations

import contextlib
import os

from fastapi import HTTPException

from clearscript.config import Config, ensure_dirs, load_config
from clearscript.ingest.json_ingest import JsonAdapter
from clearscript.ingest.md import MdAdapter
from clearscript.ingest.srt import SrtAdapter
from clearscript.ingest.txt import TxtAdapter
from clearscript.ingest.vtt import VttAdapter
from clearscript.library import Library, install_seed_pack
from clearscript.providers import build_provider

FORMAT_ADAPTERS = {
    "txt": TxtAdapter,
    "md": MdAdapter,
    "srt": SrtAdapter,
    "vtt": VttAdapter,
    "json": JsonAdapter,
}


class AppState:
    """Per-app lazy config + library factory + provider resolution."""

    def __init__(self) -> None:
        self._config: Config | None = None
        self._seed_installed = False

    def cfg(self) -> Config:
        if self._config is None:
            c = load_config()
            ensure_dirs(c)
            self._config = c
        return self._config

    def open_library(self) -> Library:
        lib = Library(self.cfg().library_path)
        # On first server boot, install the universal seed pack so the model
        # catches well-known ASR errors (DeFi → Dify, Tabby → Tavily, etc.)
        # without the user having to teach them.
        if not self._seed_installed:
            # Idempotent: add_term + add_negative skip rows that already
            # exist by canonical+scope, so calling on every boot is safe
            # even when the user already has data.
            with contextlib.suppress(Exception):
                install_seed_pack(lib, only_if_empty=False)
            self._seed_installed = True
        return lib

    def resolve_pipeline_pieces(
        self, provider_name: str | None, model_name: str | None
    ) -> tuple[object, str]:
        c = self.cfg()
        try:
            provider_cfg = c.get_provider(provider_name)
        except KeyError as exc:
            raise HTTPException(400, str(exc)) from exc

        chosen_model = model_name or provider_cfg.default_model
        if not chosen_model:
            raise HTTPException(
                400,
                f"No model specified and provider {provider_cfg.name!r} has no default. "
                "Pick one in the model dropdown.",
            )

        try:
            llm = build_provider(provider_cfg)
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc
        return llm, chosen_model


def key_source(p) -> str | None:  # type: ignore[no-untyped-def]
    """Return where a provider's API key came from, for UI display.

    Values: 'inline' (api_key in TOML), 'keyring' (set via web UI),
    'env' (env var), or None if no key found. Ollama needs no key.
    """
    if p.type == "ollama":
        return "none-needed"
    if p.api_key:
        return "inline"
    try:
        import keyring

        if keyring.get_password("clearscript", p.name):
            return "keyring"
    except Exception:
        pass
    if p.api_key_env and os.environ.get(p.api_key_env):
        return "env"
    return None
