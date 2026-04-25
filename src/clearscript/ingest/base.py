"""Common types and base class for ingest adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Segment:
    """One coherent block of speech from a single speaker."""

    text: str
    speaker_raw: str | None = None
    start_sec: float | None = None
    end_sec: float | None = None
    confidence: float | None = None


@dataclass
class NormalizedTranscript:
    """Format-agnostic representation of a parsed transcript."""

    segments: list[Segment]
    source_format: str
    source_path: Path | None = None
    detected_speakers: list[str] = field(default_factory=list)
    duration_sec: float | None = None
    raw_metadata: dict[str, object] = field(default_factory=dict)

    def to_markdown(self) -> str:
        """Render as a minimal markdown transcript (pre-edit)."""
        lines: list[str] = []
        last_speaker: str | None = None
        for seg in self.segments:
            spk = seg.speaker_raw or "?"
            if spk != last_speaker:
                if lines:
                    lines.append("")
                lines.append(f"{spk}:")
                last_speaker = spk
            lines.append(f"- {seg.text}")
        return "\n".join(lines)

    @property
    def total_text_length(self) -> int:
        return sum(len(s.text) for s in self.segments)


class IngestAdapter(ABC):
    """Subclass to support a new ASR-tool format."""

    name: str
    extensions: tuple[str, ...] = ()

    @abstractmethod
    def matches(self, path: Path, head: str) -> bool:
        """Return True if this adapter should handle the file.

        ``head`` is the first ~4 KB of the file content for content sniffing.
        """

    @abstractmethod
    def parse(self, path: Path) -> NormalizedTranscript:
        """Parse the file into a NormalizedTranscript."""
