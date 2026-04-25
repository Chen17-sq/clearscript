"""Prompt library for the clearscript pipeline.

Prompts are stored as markdown files in this package. Loading is done via
`load_prompt(name)` which respects user overrides at
`~/.config/clearscript/prompts/`.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from platformdirs import user_config_dir

_USER_OVERRIDE_DIR = Path(user_config_dir("clearscript")) / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt by relative name (e.g., 'system_base', 'stages/01_prescan', 'layers/l1_speaker').

    User overrides at ``~/.config/clearscript/prompts/<name>.md`` take precedence
    over the bundled defaults.
    """
    rel_path = f"{name}.md"

    user_path = _USER_OVERRIDE_DIR / rel_path
    if user_path.is_file():
        return user_path.read_text(encoding="utf-8")

    parts = name.split("/")
    pkg = "clearscript.prompts"
    for part in parts[:-1]:
        pkg = f"{pkg}.{part}"
    filename = f"{parts[-1]}.md"
    return resources.files(pkg).joinpath(filename).read_text(encoding="utf-8")


def compose_edit_prompt(briefing_context: str = "", library_context: str = "") -> str:
    """Compose the full prompt for the layered-edit stage."""
    parts = [
        load_prompt("system_base"),
        "\n\n---\n\n",
        load_prompt("stages/04_layered_edit"),
        "\n\n---\n\n## Layer specifications\n\n",
    ]
    for layer in (
        "l1_speaker",
        "l2_trim",
        "l3_asr_fix",
        "l3_5_sentence",
        "l4_preserve",
        "l5_format",
        "l6_punct",
    ):
        parts.append(f"### {layer.upper().replace('_', ' ')}\n\n")
        parts.append(load_prompt(f"layers/{layer}"))
        parts.append("\n\n")

    if briefing_context:
        parts.append("---\n\n## Session briefing (user-provided)\n\n")
        parts.append(briefing_context)
        parts.append("\n\n")

    if library_context:
        parts.append("---\n\n## Library hints for this chunk\n\n")
        parts.append(library_context)
        parts.append("\n\n")

    return "".join(parts)


__all__ = ["compose_edit_prompt", "load_prompt"]
