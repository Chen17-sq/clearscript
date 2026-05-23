"""Tests for the pleasantry filter that keeps mic-check chitchat out of project slugs.

Background: in v0.0.7-v0.0.9 several projects ended up with slugs like
``20260426-150-那咱们就开始吧`` because the speaker said "好的, 那咱们就
开始吧" before the actual content started. The filter rejects those opening
lines so the slug falls back to the second-line / title / timestamp.
"""

from __future__ import annotations

from clearscript.server import _looks_like_pleasantry, _slug_hint_from_input


class TestLooksLikePleasantry:
    """Direct unit tests of the startswith-based filter."""

    def test_chinese_mic_check_phrases(self) -> None:
        for line in [
            "测一下麦",
            "测试一下听得见吗",
            "听得见吗",
            "听不听得见",
            "好的",
            "好的，那咱们就开始吧",
            "那咱们就开始吧",
            "我先简单介绍一下",
            "请讲",
            "嗯",
            "对",
        ]:
            assert _looks_like_pleasantry(line), f"should filter: {line!r}"

    def test_english_mic_check_phrases(self) -> None:
        for line in [
            "ok let's go",
            "OK, let's start",
            "hello can you hear me",
            "Hello?",
        ]:
            assert _looks_like_pleasantry(line), f"should filter: {line!r}"

    def test_real_content_passes_through(self) -> None:
        # These should NOT be filtered — they're meaningful first lines.
        for line in [
            "Anthropic 这家公司最近的融资情况",
            "我们今天聊一下你对 GEO 的看法",
            "Background check on the founder's previous startup",
            "公司 ABC 的合规问题",
        ]:
            assert not _looks_like_pleasantry(line), f"should not filter: {line!r}"

    def test_empty_or_whitespace_filtered_too(self) -> None:
        # The filter rejects anything <6 chars (after strip()) — empty
        # strings and "ok" both fall under that rule. That's intentional:
        # we'd rather over-reject and fall back to "transcript" than slug
        # from junk.
        assert _looks_like_pleasantry("")
        assert _looks_like_pleasantry("   ")

    def test_case_insensitive_for_english(self) -> None:
        assert _looks_like_pleasantry("HELLO?")
        assert _looks_like_pleasantry("Ok")


class TestSlugHintFromInput:
    """Direct tests for the slug-hint helper used by /api/run.

    Priority order documented in server.py: title > filename > briefing >
    first non-pleasantry speaker turn > "transcript" fallback.
    """

    def test_title_wins_over_everything(self) -> None:
        hint = _slug_hint_from_input(
            "Speaker 1: real content here",
            "some_file.txt",
            title="Acme Ref Check",
            briefing="briefing text",
        )
        assert hint == "Acme Ref Check"

    def test_filename_stem_when_no_title(self) -> None:
        hint = _slug_hint_from_input(
            "Speaker 1: content",
            "founder_interview.docx",
        )
        assert hint == "founder_interview"

    def test_briefing_first_line_when_no_title_or_filename(self) -> None:
        hint = _slug_hint_from_input(
            "Speaker 1: anything",
            None,
            briefing="Acme CTO interview\nMore context here",
        )
        assert hint.startswith("Acme CTO interview")

    def test_first_real_speaker_turn_used(self) -> None:
        """Pleasantries get skipped; first meaningful line becomes the slug."""
        text = (
            "Speaker 1: 测一下麦\n"
            "Speaker 2: 听得见\n"
            "Speaker 1: 好的, 那咱们就开始吧\n"
            "Speaker 1: 今天聊 Anthropic 这家公司的融资情况\n"
        )
        hint = _slug_hint_from_input(text, None)
        assert "Anthropic" in hint

    def test_fallback_to_transcript_when_nothing_qualifies(self) -> None:
        hint = _slug_hint_from_input(
            "Speaker 1: 测\nSpeaker 2: ok",
            None,
        )
        # Everything was filtered → fallback string.
        assert hint == "transcript"

    def test_slug_truncated_to_50_chars(self) -> None:
        long_title = "A" * 200
        hint = _slug_hint_from_input(None, None, title=long_title)
        assert len(hint) <= 50

    def test_pleasantry_filename_falls_through(self) -> None:
        """A file named 'ok.txt' must not become the slug."""
        hint = _slug_hint_from_input(
            "Speaker 1: Founder background check on Acme",
            "ok.txt",
        )
        # The filename stem 'ok' is < 6 chars → pleasantry. Falls through
        # to transcript content.
        assert "Acme" in hint or hint == "transcript"
