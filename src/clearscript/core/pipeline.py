"""Minimum-viable pipeline (v0.0.1).

Single-pass: ingest → compose prompts → call LLM once → write output.
Future versions add chunking, per-stage artifacts, batch-ask, re-scan, etc.
The full pipeline contract lives in ``docs/architecture.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from clearscript.ingest import NormalizedTranscript, parse
from clearscript.prompts import compose_edit_prompt
from clearscript.providers import ChatMessage, LLMProvider

if TYPE_CHECKING:
    from clearscript.library import Library


@dataclass
class EditResult:
    edited_markdown: str
    change_log: list[dict[str, object]] = field(default_factory=list)
    raw_response: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    provider: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


CHANGELOG_DELIMITER = "---CHANGELOG---"


@dataclass
class Pipeline:
    provider: LLMProvider
    model: str
    library: Library | None = None
    briefing_context: str = ""
    temperature: float = 0.0
    max_tokens: int = 8192

    def run(self, input_path: Path) -> EditResult:
        transcript = parse(input_path)
        return self.run_on_transcript(transcript)

    def run_on_transcript(self, transcript: NormalizedTranscript) -> EditResult:
        library_context = self._collect_library_context(transcript)
        system_prompt = compose_edit_prompt(
            briefing_context=self.briefing_context,
            library_context=library_context,
        )

        user_prompt = self._build_user_prompt(transcript)

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]

        response = self.provider.chat(
            messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        edited, changelog = self._split_output(response.text)

        return EditResult(
            edited_markdown=edited,
            change_log=changelog,
            raw_response=response.text,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            model=response.model,
            provider=response.provider,
        )

    def _build_user_prompt(self, transcript: NormalizedTranscript) -> str:
        return (
            "Apply the layered edit pipeline (L1 through L6, including L3.5) to the transcript "
            "below. Output the cleaned markdown transcript first, then the line "
            f"`{CHANGELOG_DELIMITER}` on its own line, then the JSON change log.\n\n"
            "Raw transcript:\n\n"
            "```\n"
            f"{transcript.to_markdown()}\n"
            "```"
        )

    def _collect_library_context(self, transcript: NormalizedTranscript) -> str:
        if self.library is None:
            return ""

        lines: list[str] = []
        for spk in transcript.detected_speakers:
            hit = self.library.lookup_speaker(spk)
            if hit:
                lines.append(
                    f"- ASR speaker {spk!r} → use canonical label `{hit.display_label}` "
                    f"(real name: {hit.canonical_name})"
                )
        if lines:
            return "Speaker mappings from your library:\n" + "\n".join(lines)
        return ""

    @staticmethod
    def _split_output(text: str) -> tuple[str, list[dict[str, object]]]:
        if CHANGELOG_DELIMITER not in text:
            return text.strip(), []

        edited, _, changelog_part = text.partition(CHANGELOG_DELIMITER)
        edited = edited.strip()
        changelog_part = changelog_part.strip()
        if changelog_part.startswith("```"):
            lines = changelog_part.splitlines()
            lines = [line for line in lines if not line.startswith("```")]
            changelog_part = "\n".join(lines).strip()

        try:
            parsed_log = json.loads(changelog_part)
        except json.JSONDecodeError:
            parsed_log = []
        return edited, parsed_log if isinstance(parsed_log, list) else []
