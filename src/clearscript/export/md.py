"""Markdown exporter — the LLM output is already markdown, so this just writes."""

from __future__ import annotations

from pathlib import Path


def write_markdown(content: str, output_path: Path, *, title: str | None = None) -> Path:
    body = content.strip()
    if title:
        body = f"# {title}\n\n{body}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(body + "\n", encoding="utf-8")
    return output_path
