# L1: Speaker Identity Normalization

Normalize all speaker labels to canonical form before doing any other
edits. Most ASR tools either guess speakers badly (`Speaker 1` /
`Speaker 2`) or split one person across multiple labels (`Speaker 2` for
the first 5 minutes, `Speaker 3` after a brief silence — same person).
L1 fixes this so downstream layers see a clean speaker map.

## Step 1 — Read the whole chunk once before relabeling

Before writing any label changes, scan the transcript to figure out:

1. **How many distinct speakers are there really?** ASR commonly
   over-splits — if `Speaker 2` and `Speaker 3` say similar things in
   similar style and never overlap, they may be one person.
2. **Who is the interviewer vs. interviewee?** Interviewers tend to
   ask questions (`你们怎么...?`, `What was the founding story?`),
   give short backchannels (`好的`, `OK`, `got it`), and bridge between
   topics. Interviewees give the long answers with the substantive
   content.
3. **Are there self-introductions?** A speaker saying "我是 X" / "I'm
   X" / "我之前在 Y 工作" right after a label is a strong signal of
   that label's real identity.

## Step 2 — Apply user-supplied identities first

The user's briefing + library are ground truth. If briefing says
"Speaker 1 = Siqi, Speaker 2 = founder", apply that mapping
mechanically. If library has confirmed speaker aliases, apply those.

## Step 3 — Infer remaining speakers from content

For speakers not covered by briefing/library:

- **Interviewer**: short turns, mostly questions and backchannels →
  use `访谈者：` if no real name, OR infer from context (host of
  the show, the analyst named in briefing, etc.)
- **Interviewee**: long, content-rich turns → use the real name if
  mentioned in self-introduction or in briefing, else `受访者：`
- **Multiple interviewees**: distinguish by content (the founder vs.
  the CTO based on what they take ownership of). If you genuinely
  can't tell, leave as `受访者A：` / `受访者B：` and emit a
  SUGGESTIONS entry.

## Step 4 — Consolidate over-split speakers

If two adjacent labels (`Speaker 2` then `Speaker 3` two turns later
with no apparent reason) clearly belong to the same person — same
voice patterns, same first-person references, same role — merge them
under one label. Log it.

## Display label rules

1. **Use the user's preferred display label** from their library.
   Common patterns:
   - English first name + full-width colon (for CJK transcripts):
     `Siqi：`
   - English first name + ASCII colon (for English transcripts):
     `Siqi:`
   - Chinese given name + full-width colon: `刘勋：`
   - Anonymized fallback: `受访者：` (interviewee). Never `Speaker N`.
     Never job title as the label.
2. **Use full-width colon (`：`)** for Chinese-context labels; ASCII
   colon (`:`) for English-context.
3. **Strip extra ASR formatting** like `[user]:` or `[host]:` brackets.
4. **Same person, multiple ASR transcriptions** must unify to one
   canonical. If "阿丽 / 安丽 / 艾迪" all refer to one person named
   Eileen, use `Eileen：` everywhere — AND add the alias set to
   SUGGESTIONS so the library compounds.

## Format

- Speaker label on its own line, no leading bullet, with a blank line
  before it (except the very first speaker).
- Speaker content follows on subsequent lines.

## Example

Before (ASR output):
```
[Speaker 1]: Hi everyone, can you hear me?
[Speaker 2]: 嗯, 听得见. 我是 Eileen, 我之前在 Acme 做了 5 年的 CTO.
[Speaker 1]: 太好了. 那你们当时怎么决定 founder 这件事的?
[Speaker 3]: 主要是因为...
[user]: Got it.
```

Inference: Speaker 1 = interviewer (Siqi from briefing). Speaker 2 and
Speaker 3 are both Eileen — Speaker 2 self-introduced, Speaker 3 starts
a long answer to Siqi's question with no intervening speaker change.

After (with briefing: Speaker 1 = Siqi, Speaker 2 = Eileen):
```
Siqi：
- Hi everyone, can you hear me?

Eileen：
- 嗯, 听得见. 我是 Eileen, 我之前在 Acme 做了 5 年的 CTO.

Siqi：
- 太好了. 那你们当时怎么决定 founder 这件事的?

Eileen：
- 主要是因为...

Siqi：
- Got it.
```

Changelog entries:
```json
[
  {"layer": "L1", "old": "[Speaker 1]", "new": "Siqi：", "reason": "briefing speaker map", "confidence": 1.0},
  {"layer": "L1", "old": "[Speaker 2]", "new": "Eileen：", "reason": "briefing + self-intro confirms", "confidence": 0.99},
  {"layer": "L1", "old": "[Speaker 3]", "new": "Eileen：", "reason": "merged with Speaker 2 — same person, ASR oversplit after 沉默", "confidence": 0.85},
  {"layer": "L1", "old": "[user]", "new": "Siqi：", "reason": "ASR bracket label, content fits interviewer pattern", "confidence": 0.9}
]
```
