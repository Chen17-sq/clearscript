"""Slug derivation + SSE encoding helpers shared by the API routers."""

from __future__ import annotations

import json
from pathlib import Path

# Opening / mic-check phrases that should NOT become project slugs.
# Matched as a STARTSWITH check (not substring) so we catch "好的, 那咱们就
# 开始吧。我先简单介绍一下..." even though the line is long.
_PLEASANTRY_PATTERNS = (
    "测",  # 测一下麦 / 测试
    "听得见",
    "听不听得见",
    "能听见",
    "可以听到",
    "好的",  # 好的, 那咱们就开始吧
    "那咱们",  # 那咱们就开始吧
    "我先",  # 我先简单介绍一下
    "请",  # 请你简单介绍一下
    "没问题",
    "嗯",  # 嗯嗯
    "对",  # 对对对
    "hello",
    "hi ",
    "hi.",
    "hi!",
    "can you hear",
    "test",
    "okay",
    "ok ",
    "ok.",
    "ok,",
    "let me",
    "let's",
    "could you",
    "would you",
    "first of all",
)


def _sse_format(event_name: str, data: dict) -> str:
    """Encode a dict payload as a single Server-Sent Event."""
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _looks_like_pleasantry(text: str) -> bool:
    """Return True if `text` looks like a transcript opener / mic check / chitchat.

    We're aggressive on purpose — over-rejecting lines just falls through to
    "transcript" as the slug fallback, which is better than ending up with
    "好的-那咱们就开始吧-我先简单介绍一下今天的主题".

    Rule: STARTSWITH any pleasantry pattern OR shorter than 6 chars.
    """
    lower = text.lower().strip()
    if len(lower) < 6:
        return True
    return any(lower.startswith(p) for p in _PLEASANTRY_PATTERNS)


def _slug_hint_from_input(
    text: str | None,
    filename: str | None,
    *,
    title: str | None = None,
    briefing: str | None = None,
) -> str:
    """Pick a project slug hint, preferring user-provided context over auto-extracted text.

    Priority order:
    1. Explicit title
    2. Filename stem
    3. First proper-noun-looking phrase from briefing
    4. First non-pleasantry speaker turn from the transcript
    5. Fallback "transcript"
    """
    if title and title.strip():
        return title.strip()[:50]
    if filename:
        # Filenames are deliberately chosen by the user — don't run the
        # mic-check heuristics on them (a legit "好的会议.docx" or a short
        # stem like "ref1" used to get rejected by the <6-chars rule).
        stem = Path(filename).stem.strip()
        if stem:
            return stem[:50]
    if briefing and briefing.strip():
        # Take the first 50 chars of the briefing as a hint
        first_line = briefing.strip().splitlines()[0].strip()
        if first_line and not _looks_like_pleasantry(first_line):
            return first_line[:50]
    if text:
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            content = line
            for delim in (":", "："):
                if delim in line:
                    content = line.split(delim, 1)[1].strip()
                    break
            if not content:
                continue
            if _looks_like_pleasantry(content):
                continue
            return content[:50]
    return "transcript"
