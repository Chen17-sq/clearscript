"""Tests for project history storage."""

from __future__ import annotations

from pathlib import Path

from clearscript.storage import ProjectStore


def test_create_and_save_run_persists_all_artifacts(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create("Acme CTO interview")
    project.save_run(
        title="Acme CTO interview",
        format_="txt",
        provider="claude",
        model="claude-opus-4-7",
        input_text="Speaker 1: hi.\nSpeaker 2: hi.",
        briefing="Speaker 1 = host; Speaker 2 = founder",
        edited_markdown="Siqi：\n- hi.\n\nFounder：\n- hi.",
        change_log=[
            {"layer": "L1", "old": "Speaker 1", "new": "Siqi", "reason": "briefing"},
        ],
        suggestions=[
            {"kind": "speaker", "canonical_name": "Founder", "display_label": "Founder："},
        ],
        input_tokens=100,
        output_tokens=50,
        duration_sec=12.3,
    )

    assert project.meta_path.is_file()
    assert project.cleaned_md_path.is_file()
    assert project.change_log_path.is_file()
    assert project.suggestions_path.is_file()
    assert project.briefing_path.is_file()

    # raw input written under raw/input.txt
    raw_files = list(project.raw_dir.glob("input.*"))
    assert len(raw_files) == 1
    assert raw_files[0].read_text(encoding="utf-8").startswith("Speaker 1:")


def test_summary_extracts_meta(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create("interview")
    project.save_run(
        title="My run",
        format_="md",
        provider="deepseek",
        model="deepseek-chat",
        input_text="Speaker 1: hi.",
        edited_markdown="Output",
        change_log=[],
        suggestions=[],
        input_tokens=50,
        output_tokens=25,
    )
    summary = project.summary()
    assert summary["title"] == "My run"
    assert summary["format"] == "md"
    assert summary["provider"] == "deepseek"
    assert summary["model"] == "deepseek-chat"
    assert summary["total_tokens"] == 75
    assert summary["change_count"] == 0


def test_detail_includes_all_payload(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create("x")
    project.save_run(
        title="X",
        format_="txt",
        provider="claude",
        model="opus",
        input_text="raw input here",
        briefing="some briefing",
        edited_markdown="cleaned",
        change_log=[{"layer": "L3", "old": "a", "new": "b"}],
        suggestions=[{"kind": "term", "canonical": "Dify"}],
        input_tokens=1,
        output_tokens=2,
    )
    d = project.detail()
    assert d["title"] == "X"
    assert "raw input" in d["raw_input"]
    assert "cleaned" in d["cleaned_markdown"]
    assert d["briefing"] == "some briefing"
    assert len(d["change_log"]) == 1
    assert len(d["suggestions"]) == 1


def test_list_summaries_sorted_newest_first(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    p1 = store.create("first")
    p1.save_run(
        title="first",
        format_="txt",
        provider="m",
        model="m",
        input_text="a",
        edited_markdown="b",
        change_log=[],
        suggestions=[],
        input_tokens=0,
        output_tokens=0,
    )
    # Force second project to have a later timestamp by manipulating its meta directly.
    p2 = store.create("second")
    meta = p2.read_meta()
    meta["created_at"] = "2099-12-31T23:59:59"
    p2.write_meta(meta)
    p2.cleaned_md_path.write_text("ok", encoding="utf-8")

    summaries = store.list_summaries()
    assert len(summaries) == 2
    assert summaries[0]["slug"] == p2.slug


def test_delete_removes_directory(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create("doomed")
    project.save_run(
        title="x",
        format_="txt",
        provider="m",
        model="m",
        input_text="a",
        edited_markdown="b",
        change_log=[],
        suggestions=[],
        input_tokens=0,
        output_tokens=0,
    )
    assert project.root.is_dir()
    assert store.delete(project.slug)
    assert not project.root.exists()
    assert not store.exists(project.slug)


def test_delete_nonexistent_returns_false(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    assert not store.delete("does-not-exist")


def test_slug_includes_seconds_so_two_quick_runs_differ(tmp_path: Path) -> None:
    import time

    store = ProjectStore(tmp_path)
    s1 = store.slug_for("foo")
    time.sleep(1.1)
    s2 = store.slug_for("foo")
    assert s1 != s2


def test_binary_input_written_as_bytes(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create("binfile")
    fake_docx = b"PK\x03\x04not-really-but-binary"
    project.save_run(
        title=None,
        format_="docx",
        provider="m",
        model="m",
        input_bytes=fake_docx,
        input_filename="meeting.docx",
        edited_markdown="cleaned",
        change_log=[],
        suggestions=[],
        input_tokens=0,
        output_tokens=0,
    )
    raw_files = list(project.raw_dir.glob("*.docx"))
    assert len(raw_files) == 1
    assert raw_files[0].read_bytes() == fake_docx
    # And detail() doesn't choke on binary
    detail = project.detail()
    assert detail["raw_input"] == ""  # binary returns empty string, not crash


def test_read_input_returns_text_and_format(tmp_path: Path) -> None:
    """Project.read_input is the foundation of the rerun feature.

    It must return the original input text plus its format extension so the
    pipeline can re-parse it with the right adapter.
    """
    store = ProjectStore(tmp_path)
    project = store.create("rerun-source")
    project.save_run(
        title="Source",
        format_="srt",
        provider="claude",
        model="opus",
        input_text="1\n00:00:01,000 --> 00:00:02,000\nSpeaker A: Hi.",
        edited_markdown="cleaned",
        change_log=[],
        suggestions=[],
        input_tokens=10,
        output_tokens=5,
    )
    result = project.read_input()
    assert result is not None
    text, fmt = result
    assert "Speaker A: Hi." in text
    assert fmt == "srt"


def test_read_input_returns_none_for_binary(tmp_path: Path) -> None:
    """Binary inputs (e.g. docx) can't be replayed via rerun — return None."""
    store = ProjectStore(tmp_path)
    project = store.create("binary-source")
    # Pack of bytes that's not valid utf-8.
    project.save_run(
        title=None,
        format_="docx",
        provider="m",
        model="m",
        input_bytes=b"\xff\xfe\x00\x01PK\x03\x04binary garbage",
        input_filename="meeting.docx",
        edited_markdown="cleaned",
        change_log=[],
        suggestions=[],
        input_tokens=0,
        output_tokens=0,
    )
    assert project.read_input() is None


def test_read_briefing_handles_missing_file(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create("no-briefing")
    project.save_run(
        title="",
        format_="txt",
        provider="m",
        model="m",
        input_text="hi",
        edited_markdown="hi",
        change_log=[],
        suggestions=[],
        input_tokens=0,
        output_tokens=0,
    )
    assert project.read_briefing() == ""


def test_create_rerun_of_uses_parent_slug_tail(tmp_path: Path) -> None:
    """The rerun slug includes the original's meaningful tail + '-rerun'."""
    store = ProjectStore(tmp_path)
    orig = store.create("Acme CTO interview")
    # Slug format: 2026-05-16-143012-acme-cto-interview
    assert "acme-cto-interview" in orig.slug

    rerun = store.create_rerun_of(orig.slug)
    assert rerun.slug != orig.slug
    assert rerun.slug.endswith("-rerun")
    assert "acme-cto-interview" in rerun.slug
