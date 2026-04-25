"""Generic plain-text ASR adapter.

Heuristics:
- Lines matching ``Speaker N: ...`` or ``[Speaker N] ...`` are split as new turns.
- Lines matching ``<name>: <text>`` (where name is short) are treated as speaker turns.
- Otherwise, lines are appended to the most-recent speaker's segment.
"""

from __future__ import annotations

import re
from pathlib import Path

from clearscript.ingest.base import IngestAdapter, NormalizedTranscript, Segment

_SPEAKER_PATTERNS = [
    re.compile(r"^\s*\[?(Speaker\s*\d+)\]?\s*[:：]\s*(.*)$", re.IGNORECASE),
    re.compile(r"^\s*\[([^\]]{1,30})\]\s*[:：]?\s*(.*)$"),
    re.compile(r"^\s*([\w一-龥][\w\s一-龥\.-]{0,20}?)\s*[:：]\s*(.+)$"),
]

_TIMESTAMP_PATTERN = re.compile(r"^\s*\[?(\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?)\]?\s+")


class TxtAdapter(IngestAdapter):
    name = "txt"
    extensions = (".txt",)

    def matches(self, path: Path, head: str) -> bool:
        return path.suffix.lower() in self.extensions

    def parse(self, path: Path) -> NormalizedTranscript:
        content = path.read_text(encoding="utf-8")
        return self.parse_string(content, path)

    def parse_string(
        self, content: str, source_path: Path | None = None
    ) -> NormalizedTranscript:
        """Parse raw text content (no file I/O). Used by the web UI for paste-in input."""
        return self._parse_text(content, source_path)

    def _parse_text(self, content: str, path: Path | None) -> NormalizedTranscript:
        segments: list[Segment] = []
        current_speaker: str | None = None
        current_lines: list[str] = []
        seen_speakers: list[str] = []

        def flush() -> None:
            if current_lines:
                segments.append(
                    Segment(
                        text=" ".join(s.strip() for s in current_lines if s.strip()),
                        speaker_raw=current_speaker,
                    )
                )

        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            if not line:
                continue

            line = _TIMESTAMP_PATTERN.sub("", line, count=1)

            speaker, text = self._try_split_speaker(line)
            if speaker is not None:
                flush()
                current_speaker = speaker
                if speaker not in seen_speakers:
                    seen_speakers.append(speaker)
                current_lines = [text] if text else []
            else:
                current_lines.append(line)

        flush()

        return NormalizedTranscript(
            segments=segments,
            source_format=self.name,
            source_path=path,
            detected_speakers=seen_speakers,
        )

    def _try_split_speaker(self, line: str) -> tuple[str | None, str]:
        for pattern in _SPEAKER_PATTERNS:
            m = pattern.match(line)
            if m:
                speaker = m.group(1).strip()
                text = m.group(2).strip()
                if self._looks_like_speaker(speaker):
                    return speaker, text
        return None, line

    @staticmethod
    def _looks_like_speaker(token: str) -> bool:
        if not token:
            return False
        if len(token) > 25:
            return False
        return token.count(" ") <= 3
