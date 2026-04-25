"""Tests for the txt ingest adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from clearscript.ingest import parse
from clearscript.ingest.txt import TxtAdapter


def write_tmp(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "transcript.txt"
    p.write_text(content, encoding="utf-8")
    return p


def test_parses_speaker_n_labels(tmp_path: Path) -> None:
    content = """Speaker 1: Hi everyone, can you hear me?
Speaker 2: Yes I can.
Speaker 1: Great, let's start.
"""
    transcript = parse(write_tmp(tmp_path, content))
    assert len(transcript.segments) == 3
    assert transcript.segments[0].speaker_raw == "Speaker 1"
    assert transcript.segments[1].speaker_raw == "Speaker 2"
    assert "Hi everyone" in transcript.segments[0].text


def test_parses_bracketed_labels(tmp_path: Path) -> None:
    content = """[Aldrich]: Question one?
[Interviewee]: Answer one.
"""
    transcript = parse(write_tmp(tmp_path, content))
    assert len(transcript.segments) == 2
    assert transcript.segments[0].speaker_raw == "Aldrich"
    assert transcript.segments[1].speaker_raw == "Interviewee"


def test_parses_chinese_full_width_colon(tmp_path: Path) -> None:
    content = """张三：你好。
李四：你好啊。
"""
    transcript = parse(write_tmp(tmp_path, content))
    assert len(transcript.segments) == 2
    assert transcript.segments[0].speaker_raw == "张三"
    assert transcript.segments[1].speaker_raw == "李四"


def test_strips_leading_timestamp(tmp_path: Path) -> None:
    content = """[00:14:33] Speaker 1: Hello there.
"""
    transcript = parse(write_tmp(tmp_path, content))
    assert len(transcript.segments) == 1
    assert transcript.segments[0].speaker_raw == "Speaker 1"
    assert "Hello there" in transcript.segments[0].text


def test_continuation_lines_attach_to_speaker(tmp_path: Path) -> None:
    content = """Speaker 1: First sentence.
This continues the same turn.
And so does this.
Speaker 2: New speaker.
"""
    transcript = parse(write_tmp(tmp_path, content))
    assert len(transcript.segments) == 2
    assert "continues" in transcript.segments[0].text
    assert transcript.segments[1].speaker_raw == "Speaker 2"


def test_to_markdown_format(tmp_path: Path) -> None:
    content = "Speaker 1: Hi.\nSpeaker 2: Hello.\n"
    md = parse(write_tmp(tmp_path, content)).to_markdown()
    assert "Speaker 1:" in md
    assert "- Hi." in md
    assert "Speaker 2:" in md


def test_unknown_extension_raises(tmp_path: Path) -> None:
    p = tmp_path / "transcript.unknown"
    p.write_text("anything", encoding="utf-8")
    with pytest.raises(ValueError, match="No ingest adapter"):
        parse(p)


def test_adapter_matches_extension() -> None:
    adapter = TxtAdapter()
    assert adapter.matches(Path("foo.txt"), "")
    assert not adapter.matches(Path("foo.docx"), "")
