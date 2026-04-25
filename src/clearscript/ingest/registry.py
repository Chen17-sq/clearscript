"""Ingest adapter registry and dispatch.

Detection is layered: extension first, content sniffing second. The first
adapter to ``matches()`` wins.
"""

from __future__ import annotations

from pathlib import Path

from clearscript.ingest.base import IngestAdapter, NormalizedTranscript
from clearscript.ingest.txt import TxtAdapter

_ADAPTERS: list[IngestAdapter] = [TxtAdapter()]


def register_adapter(adapter: IngestAdapter) -> None:
    """Register a custom adapter (used by user plugins)."""
    _ADAPTERS.insert(0, adapter)


def detect_format(path: Path) -> IngestAdapter:
    """Return the first adapter that claims the file."""
    head = ""
    if path.is_file():
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:4096]
        except OSError:
            head = ""

    for adapter in _ADAPTERS:
        if adapter.matches(path, head):
            return adapter

    raise ValueError(
        f"No ingest adapter matched {path}. "
        f"Supported extensions in v0.0.1: {[ext for a in _ADAPTERS for ext in a.extensions]}"
    )


def parse(path: Path) -> NormalizedTranscript:
    """Parse a file into a NormalizedTranscript using the right adapter."""
    adapter = detect_format(path)
    return adapter.parse(path)
