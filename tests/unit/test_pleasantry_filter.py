"""Tests for the pleasantry filter that keeps mic-check chitchat out of project slugs.

Background: in v0.0.7-v0.0.9 several projects ended up with slugs like
``20260426-150-那咱们就开始吧`` because the speaker said "好的, 那咱们就
开始吧" before the actual content started. The filter rejects those opening
lines so the slug falls back to the second-line / title / timestamp.
"""

from __future__ import annotations

from clearscript.server import _looks_like_pleasantry


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
