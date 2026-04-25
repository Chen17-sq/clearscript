# L3.5: Sentence-level reasoning cleanup

L3 fixes word-level errors. L3.5 handles deeper structural issues that require reasoning over context. **This layer is conservative by design — its red line is "never fabricate content".**

## Issues to handle

| Type | Example | Action |
|---|---|---|
| Misplaced sentence boundary | "我们做的是。一个推荐系统。" | Merge: "我们做的是一个推荐系统。" |
| Repeated stutter | "我们我们当时是想……" | Dedup: "我们当时是想……" |
| Word-order garbling | "技术他做的" | If high-confidence fix exists, apply with log; else mark `[词序疑似错乱: <原文>]` and refuse |
| Missing function word | "因为那时候百度的 PM。" (incomplete) | Mark `[句子不完整: <原文>]`. **Do not autocomplete.** |
| Speaker switch swallowed | A's paragraph contains B's voice mid-sentence | Split into two speaker blocks based on content cues |
| Number/letter confusion | "五 3 个" | Resolve to "53 个" or "五十三个" only if context makes it unambiguous |
| Same-sound substitution destroying meaning | "co-host 公司" where context demands "cohort 公司" | Fix back |

## Red line: never fabricate

- **Never auto-complete a sentence the speaker abandoned.** Half-sentences stay as `[句子不完整: ...]`.
- **Never invent words to fill `[inaudible]`.** Mark and move on.
- **Never paraphrase to make broken syntax flow.** A broken sentence is data; a smoothed-over guess is fiction.

## Required confidence threshold

- Word-order rearrangements: only apply if `confidence > 0.85`
- Stutter dedup: only apply if the repetition is exact (`X X` pattern with no semantic difference)
- Speaker-switch splits: only apply if you can cite specific content evidence (different topic, different verbal style)

When unsure, mark for user review. The pipeline is designed to handle ambiguity — your job is to surface it accurately, not paper over it.
