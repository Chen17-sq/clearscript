# L3.5: Sentence-level reasoning cleanup

L3 fixes errors at the **word** level. L3.5 fixes errors at the
**sentence** level — broken syntax, garbled order, ASR sentence-boundary
mistakes, speaker-switch swallowing. This layer needs more reasoning
than L3 but stays bounded by a hard red line: **never fabricate content
the speaker didn't actually say.**

## Mandatory routine

Walk the chunk sentence by sentence. For each sentence, ask:

### Check 1 — Sentence boundary correctness

ASR commonly splits one logical sentence into two ("我们做的是。一个推
荐系统。") or merges two into one. Patterns:

- Sentence ends mid-clause (no terminal verb / no object / mid-modifier)
- Next "sentence" starts with what should be its object/complement
- A run-on with multiple subjects + no commas

**Action:** Re-segment when the fix is structurally unambiguous (the
fragments have to belong together for grammar to work). Don't
re-segment to "improve readability".

### Check 2 — Stutter / repetition dedup

ASR transcripts contain spoken repetitions:

| Pattern | Example | Action |
|---|---|---|
| Exact word repeat | "我们我们当时是想……" | Dedup: "我们当时是想……" |
| Phrase restart | "他他然后他说" | Dedup to "他说" |
| Filler-then-restart | "嗯, 嗯, 我们后来" | Drop the filler restart |
| Stutter on first syllable | "我 我 我们" | Dedup to "我们" |

Rule: only dedup when the repetition is **exact** (`X X` with no
intervening semantic content) OR clearly a stutter restart. Don't dedup
intentional emphasis ("非常非常 important").

### Check 3 — Word order garbling

ASR sometimes outputs scrambled word order ("技术他做的" should be "他
做的技术"). For each suspicious sentence:

1. If you can identify the correct order with >85% confidence AND
   the fix doesn't change meaning, apply with `confidence >= 0.85`
   and log the change.
2. If <85%, leave as `[词序疑似错乱: <原文>]` and flag for review.
3. **Don't paraphrase** to make it flow — that's fabrication.

### Check 4 — Missing function words / abandoned sentences

If a sentence trails off without a verb / object / conclusion:
"因为那时候百度的 PM。" — the speaker stopped mid-thought, OR the ASR
dropped the conclusion.

**Never auto-complete.** Mark `[句子不完整: <原文>]`. The user can
listen back if they care.

### Check 5 — Speaker switch swallowed mid-paragraph

A paragraph labeled `Speaker A:` that contains a clear B-voice
interjection mid-stream:

> Speaker A: 那我们当时就决定要做这个产品。是啊很多团队都遇到过这个
> 问题。然后我们花了三个月做 prototype。

The "是啊很多团队都遇到过这个问题" reads as a separate speaker
agreeing — different rhythm, different perspective. Split it out:

> Speaker A: 那我们当时就决定要做这个产品。
>
> Speaker B: 是啊很多团队都遇到过这个问题。
>
> Speaker A: 然后我们花了三个月做 prototype。

**Only do this** when (a) you can identify the inserted voice as one
of the established speakers (style match) and (b) the split makes the
paragraph more coherent, not less.

### Check 6 — Number/letter confusion in spoken digits

| ASR wrote | Likely meant | Why |
|---|---|---|
| "五 3 个" | "53 个" | Letter-form-of-number mixed with digit |
| "二零二六年三月" | "2026 年 3 月" | OK as-is for narration, but pick one style consistently |
| "百分之三 五" | "百分之三十五" | Dropped 十 |
| "差不多三 四百人" | "差不多三四百人" | Drop the space; preserve range |
| "two thousand and 24" | "2024" | English number narration |

Resolve only when the context is **unambiguous**. If "五 3 个" could
plausibly be "5 to 3" (in a sports / score context) vs "53" (in a
team-size context), use the surrounding context to decide. If genuinely
ambiguous, leave as-is and add a `needs_user_review` flag.

### Check 7 — Same-sound substitution destroying meaning

ASR sometimes picks the more common homophone, destroying the
speaker's intended meaning:

- "co-host 公司" where the topic is a YC-style accelerator cohort →
  speaker said "cohort 公司"
- "对面的同事" where the topic is engineering review → speaker
  probably said "对面的同事" (face-to-face colleagues), not "对面"
  (opposite). Tricky — leave unless context is overwhelming.
- "投行" vs "投航" — almost always 投行

When the homophone change clearly destroys the speaker's domain
meaning, fix it back. Log as L3.5 with reason.

## Red line: never fabricate

- **Never auto-complete a sentence the speaker abandoned.**
- **Never invent words to fill `[inaudible]`.**
- **Never paraphrase to make broken syntax flow.** A broken sentence
  is data; a smoothed-over guess is fiction.
- **Never split a paragraph into multiple speakers** unless you can
  cite specific style/voice evidence.

## Required confidence thresholds

| Change type | Min confidence |
|---|---|
| Stutter dedup (exact `X X`) | 0.95 |
| Sentence boundary merge | 0.85 |
| Word-order rearrangement | 0.85 |
| Speaker-switch split | 0.85 + content evidence |
| Number disambiguation | 0.80 + domain context |
| Homophone reversal | 0.80 + clear topic mismatch |

Below threshold: surface via `[…]` marker + `needs_user_review`. The
pipeline is designed to handle ambiguity surface area — your job is to
flag accurately, not paper over it.

## What L3.5 explicitly does NOT do

- ✗ Sentence simplification ("make it shorter")
- ✗ Removing filler words like 嗯/啊 (that's L2's job, conservatively)
- ✗ Reordering question-answer flow
- ✗ Combining consecutive questions for "efficiency"
- ✗ Translating between languages
- ✗ Adding punctuation L6 hasn't asked for

L3.5 only fixes what was clearly broken by the ASR. Everything else
flows through untouched.
