"""ASR transcript ingestion."""

from clearscript.ingest.base import IngestAdapter, NormalizedTranscript, Segment
from clearscript.ingest.registry import detect_format, parse

__all__ = [
    "IngestAdapter",
    "NormalizedTranscript",
    "Segment",
    "detect_format",
    "parse",
]
