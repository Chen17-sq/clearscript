"""Tests for exporters."""

from __future__ import annotations

from pathlib import Path

from clearscript.export import write_docx, write_markdown

SAMPLE_MD = """Speaker 1：
- Hi everyone.
- Welcome to the show.

Speaker 2：
- Thanks for having me.
  - Quick sub-point.
"""


def test_markdown_writes_with_title(tmp_path: Path) -> None:
    out = tmp_path / "out.md"
    write_markdown(SAMPLE_MD, out, title="Sample Episode")
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Sample Episode")
    assert "Speaker 1：" in text
    assert "Welcome" in text


def test_markdown_writes_without_title(tmp_path: Path) -> None:
    out = tmp_path / "out.md"
    write_markdown(SAMPLE_MD, out)
    text = out.read_text(encoding="utf-8")
    assert not text.startswith("#")


def test_docx_writes_file(tmp_path: Path) -> None:
    out = tmp_path / "out.docx"
    write_docx(SAMPLE_MD, out, title="Sample")
    assert out.is_file()
    assert out.stat().st_size > 0
