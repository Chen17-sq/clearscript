"""Pydantic request/response models for the HTTP API.

Module-level (not nested in create_app) so FastAPI can introspect them
and so tests can import them directly.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    transcript: str
    format: str | None = None  # txt / md / srt / vtt / json — drives parser choice
    provider: str | None = None
    model: str | None = None
    title: str | None = None
    briefing: str | None = None


class RunResponse(BaseModel):
    edited_markdown: str
    change_log: list[dict]
    suggestions: list[dict]
    input_tokens: int
    output_tokens: int
    model: str
    provider: str
    num_chunks: int = 1  # > 1 when the transcript was auto-chunked
    project_slug: str | None = None  # set when the run was persisted to disk


class ExportRequest(BaseModel):
    markdown: str
    title: str | None = None


class TermPayload(BaseModel):
    canonical: str = ""
    type: str | None = Field(default=None)
    domain: str | None = None
    status: str | None = None
    definition: str | None = None
    notes: str | None = None
    aliases: list[str] = []


class SpeakerPayload(BaseModel):
    canonical_name: str = ""
    display_label: str = ""
    primary_language: str | None = None
    notes: str | None = None
    aliases: list[str] = []


class PatternPayload(BaseModel):
    title: str
    trigger_desc: str
    action: str
    rationale: str | None = None
    domain: str | None = None


class SuggestionItem(BaseModel):
    kind: str
    canonical: str | None = None
    canonical_name: str | None = None
    display_label: str | None = None
    type: str | None = None
    domain: str | None = None
    aliases_seen: list[str] = []
    title: str | None = None
    trigger_desc: str | None = None
    action: str | None = None
    rationale: str | None = None


class AcceptSuggestionsRequest(BaseModel):
    suggestions: list[SuggestionItem]


class EstimateCostRequest(BaseModel):
    transcript: str
    provider: str | None = None
    model: str | None = None


class UpdateTranscriptRequest(BaseModel):
    cleaned_markdown: str


class RerunRequest(BaseModel):
    provider: str | None = None
    model: str | None = None


class BootstrapRequest(BaseModel):
    """Body for ``POST /api/library/bootstrap``.

    ``transcripts`` is a list of raw transcript strings (txt format
    assumed).
    """

    transcripts: list[str]
    provider: str | None = None
    model: str | None = None


class NegativePayload(BaseModel):
    """A negative-correction rule — 'do NOT change `text` to `do_not_change_to`'.

    Used by L3 to suppress over-eager substitutions. Common examples:
    keeping speaker colloquialisms ("蛮好的" not "很好"), preserving
    approximate phrasing ("差不多三四百人"), etc.
    """

    text: str
    do_not_change_to: str | None = None
    domain: str | None = None
    reason: str | None = None
