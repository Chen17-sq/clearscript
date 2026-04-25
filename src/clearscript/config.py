"""Configuration loading for clearscript.

Configuration sources (later overrides earlier):
1. Bundled defaults
2. ``~/.config/clearscript/config.toml``
3. Environment variables (``CLEARSCRIPT_*``)
4. CLI flags
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_data_dir

try:
    import tomllib
except ImportError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]


CONFIG_DIR = Path(user_config_dir("clearscript"))
DATA_DIR = Path(user_data_dir("clearscript"))

CONFIG_FILE = CONFIG_DIR / "config.toml"
PROVIDERS_FILE = CONFIG_DIR / "providers.toml"


@dataclass
class ProviderConfig:
    name: str
    type: str
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    default_model: str | None = None
    models: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def resolve_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.environ.get(self.api_key_env)
        return None


@dataclass
class Config:
    default_provider: str = "claude"
    default_model: str | None = None
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    library_path: Path = field(default_factory=lambda: DATA_DIR / "library" / "library.db")
    projects_root: Path = field(
        default_factory=lambda: Path.home() / "Documents" / "clearscript" / "projects"
    )

    def get_provider(self, name: str | None = None) -> ProviderConfig:
        key = name or self.default_provider
        if key not in self.providers:
            raise KeyError(
                f"Provider {key!r} not configured. Available: {list(self.providers.keys())}. "
                f"Add it to {PROVIDERS_FILE} or set ANTHROPIC_API_KEY for the default 'claude' provider."
            )
        return self.providers[key]


def _builtin_providers() -> dict[str, ProviderConfig]:
    """Provide sensible defaults so the tool works out-of-box if env vars are set."""
    return {
        "claude": ProviderConfig(
            name="claude",
            type="anthropic",
            api_key_env="ANTHROPIC_API_KEY",
            default_model="claude-opus-4-7",
            models=["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"],
        ),
        "openai": ProviderConfig(
            name="openai",
            type="openai",
            api_key_env="OPENAI_API_KEY",
            default_model="gpt-4o",
            models=["gpt-4o", "gpt-4o-mini", "o1"],
        ),
        "deepseek": ProviderConfig(
            name="deepseek",
            type="openai-compat",
            base_url="https://api.deepseek.com/v1",
            api_key_env="DEEPSEEK_API_KEY",
            default_model="deepseek-chat",
            models=["deepseek-chat", "deepseek-reasoner"],
        ),
        "gemini": ProviderConfig(
            name="gemini",
            type="google",
            api_key_env="GEMINI_API_KEY",
            default_model="gemini-2.0-flash-exp",
            models=["gemini-2.0-flash-exp", "gemini-1.5-pro"],
        ),
        "ollama": ProviderConfig(
            name="ollama",
            type="ollama",
            base_url="http://localhost:11434",
            default_model="qwen2.5:14b",
            models=[],
        ),
    }


def load_config() -> Config:
    cfg = Config(providers=_builtin_providers())

    if CONFIG_FILE.is_file():
        with CONFIG_FILE.open("rb") as f:
            data = tomllib.load(f)
        if "default_provider" in data:
            cfg.default_provider = data["default_provider"]
        if "default_model" in data:
            cfg.default_model = data["default_model"]
        if "library_path" in data:
            cfg.library_path = Path(data["library_path"]).expanduser()
        if "projects_root" in data:
            cfg.projects_root = Path(data["projects_root"]).expanduser()

    if PROVIDERS_FILE.is_file():
        with PROVIDERS_FILE.open("rb") as f:
            pdata = tomllib.load(f)
        if "default_provider" in pdata:
            cfg.default_provider = pdata["default_provider"]
        for name, raw in pdata.get("providers", {}).items():
            cfg.providers[name] = ProviderConfig(
                name=name,
                type=raw.get("type", "openai-compat"),
                base_url=raw.get("base_url"),
                api_key=raw.get("api_key"),
                api_key_env=raw.get("api_key_env"),
                default_model=raw.get("default_model"),
                models=raw.get("models", []),
                extra={
                    k: v
                    for k, v in raw.items()
                    if k
                    not in {"type", "base_url", "api_key", "api_key_env", "default_model", "models"}
                },
            )

    return cfg


def ensure_dirs(cfg: Config) -> None:
    """Create data and config directories if they don't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg.library_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.projects_root.mkdir(parents=True, exist_ok=True)
