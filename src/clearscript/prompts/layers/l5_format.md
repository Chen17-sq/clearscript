# L5: Dialogue Structure Formatting

Apply consistent formatting so the transcript reads cleanly and exports cleanly to docx, html, etc.

## Rules

1. **Speaker label on its own line**, no bullet, with a blank line in front (except the first speaker).
2. **Speaker content uses `-` short-dash bullet list** (not `•`, not `*`, not numbered).
3. **Sub-points within an answer** ("第一个……" / "第二……" / "Firstly... / Secondly...") get a 2-space indent under their parent bullet.
4. **Long answers split into multiple `-` bullets by semantic unit, not by sentence.** A bullet should be a coherent thought.
5. **Short interruptions** (1-3 chars: "对", "嗯", "right") embed as parenthetical inside the main speaker's bullet: `(打断: 对对对)` or `(interruption: right right)`.
6. **Long interruptions** become their own speaker block.

## Format example

```
Siqi：
- Could you briefly walk through your background?

受访者：
- I started out at Baidu working on advertising algorithms.
- After that I moved to a startup as Head of Recommendation.
  - The team was about 30 engineers when I joined.
  - We grew to ~80 over two years.
- Most recently I've been at the current company leading the search platform.

Siqi：
- Got it. (interruption: yes yes) And what made you leave the previous role?
```

## Anti-patterns

- Don't use numbered lists (`1. 2. 3.`) for speaker content
- Don't use heading syntax (`#`, `##`) for anything other than the document title
- Don't merge short consecutive speaker turns to "save space"
- Don't put speaker content inline with the speaker label
