# L1: Speaker Identity Normalization

Normalize all speaker labels to canonical form before doing any other edits.

## Rules

1. **Replace ASR auto-bracketed labels** (`[Speaker 1]`, `[Speaker N]`, `Speaker 2:`, etc.) with the real speaker name from the user's briefing.
2. **Same person, multiple ASR transcriptions** must unify to one canonical name. (E.g., if "阿丽 / 安丽 / 艾迪" all refer to the same person named Eileen, use `Eileen:` everywhere.)
3. **Use the user's preferred display label** from their library. Common patterns:
   - English first name + colon: `Siqi：`
   - Chinese given name + colon: `刘勋：`
   - Anonymized fallback: `受访者：` (interviewee) — never `Speaker N`, never job title as label.
4. **Use full-width colon (`：`)** for Chinese-context labels; ASCII colon (`:`) for English-context.
5. **Strip extra ASR formatting** like `[user]:` or `[host]:` brackets.

## Format

- Speaker label on its own line, no leading bullet, with a blank line before it (except the very first speaker).
- Speaker content follows on subsequent lines.

## Example

Before:
```
[Speaker 1]: Hi everyone, can you hear me?
[Speaker 2]: Yes I can. So basically my background is...
[user]: Got it.
```

After (with briefing: Speaker 1 = Siqi, Speaker 2 = the interviewee):
```
Siqi：
- Hi everyone, can you hear me?

受访者：
- Yes I can. So basically my background is...

Siqi：
- Got it.
```
