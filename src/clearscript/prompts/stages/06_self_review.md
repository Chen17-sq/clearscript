# Stage 6: Self-Review

You've just produced an edited transcript through the L1-L6 layered
pipeline. Now read it again with fresh eyes. The first pass is rarely
complete — humans miss things on first read, and so do you. This
second pass catches what the layered pass left behind.

The user has chosen to spend an extra LLM call for this review. Make
it count. Catch real errors; don't second-guess high-confidence work.

## What you'll receive

The user message contains, as plain sections:

- **Session briefing** (if any) — the user's context for this transcript
- **Library vocabulary** — canonical ← alias mappings to audit against
- **First-pass change log** — a JSON array of the edits already made
- **Cleaned transcript** — between `<<<TRANSCRIPT_START>>>` and
  `<<<TRANSCRIPT_END>>>` markers. Do NOT echo it back in your output.

## Mandatory review routine

Walk the document top to bottom. For each section, run these checks:

### 1. Proper noun audit

Re-read every capitalised English word and every CamelCase token in
the edited transcript. For each one, ask:

- **Is this a real entity?** (company, product, person, framework)
- **Does it fit the domain of the conversation?**
- **Did the first pass correct it, or did it pass through?**

If you find a token that should have been corrected but wasn't (e.g.
`Tabby` still in a conversation about web search tools), emit a
correction. The most common L3 misses are:
- Mid-sentence English nouns that the first pass treated as proper
  English words instead of misheard Chinese-context entities
- Acronyms where the expansion the first pass implied doesn't fit
  the speakers' domain
- Person names: same person rendered three ways (Eileen / 阿丽 /
  艾迪) and the first pass only caught two of three

### 2. Speaker consistency audit

Across the full document:
- **Same person rendered differently** in different sections — emit
  L1 corrections to unify.
- **A speaker label that contradicts the content** — e.g. labeled
  `Siqi:` but the content is clearly an interviewee answer, not a
  question. Fix the label.
- **A turn that's actually two speakers** that the first pass merged.
  Look for sudden role/voice shifts within one labeled block.

### 3. Cross-section data consistency

The same metric, headcount, valuation, percentage, or date mentioned
in multiple places should agree — or be flagged. Cross-check:

- ARR / revenue figures
- Team size / headcount
- Funding round amounts
- Dates of key events
- Percentages (market share, growth rate, etc.)

If you find a conflict, add it to `data_conflicts` so the user can
resolve. Don't silently pick.

### 4. Format hygiene

- Any leftover `[Speaker N]` or `[user]:` labels? Fix.
- Mixed punctuation within a sentence (`,` and `，` in the same
  Chinese sentence)? Pick one and apply.
- Bullet styles mixing (`-` vs `•` vs `·`)? Unify to `-`.
- Stray markdown artifacts (`**` partial bolds, broken `[link](text)`
  patterns from misread spoken `[brackets]`)? Clean.

### 5. Over-correction rollbacks

This is the failsafe. Look at the `change_log` for entries with:
- `confidence < 0.7`
- L3 corrections where the new value is a famous company you happen
  to know but the speaker's context doesn't actually call for it
- L3.5 word-order fixes that may have changed meaning

If any feel like fluency edits rather than true error fixes, propose
a rollback.

## Output format

A single JSON object (raw JSON preferred; a ```json fence is tolerated —
the parser strips it). No prose before or after.

```json
{
  "additional_corrections": [
    {"layer": "L1", "old": "Speaker 3:", "new": "Eileen：", "reason": "second-pass: same speaker as Eileen earlier in doc", "confidence": 0.9}
  ],
  "rollbacks": [
    {"old": "<the original phrase>", "new_to_undo": "<the first-pass replacement>", "reason": "first pass changed 'cohort 公司' to 'co-host 公司' but context demands the original 'cohort'"}
  ],
  "promotions_to_user_review": [
    {"location": "受访者 paragraph starting '我们当时'", "issue": "Number cited as 五 3 个 — ambiguous between 5/3 and 53", "options": ["五个", "三个", "五十三个"]}
  ],
  "data_conflicts": [
    {"locations": ["section near 'ARR'", "section near '年化收入'"], "metric": "ARR", "values": ["$2M", "$2.5M"]}
  ],
  "format_issues": [
    {"location": "first speaker block", "issue": "leftover [Speaker 2] label", "fix": "Eileen："}
  ]
}
```

**All fields are arrays.** Use `[]` (empty array) for any category
with no findings. Don't omit fields.

## Discipline

- **Don't second-guess high-confidence work.** If the first pass said
  L3 with confidence 0.95, leave it alone unless you see clear new
  evidence.
- **Don't introduce edits you can't justify in `reason`.** "It reads
  better" is not a reason.
- **Be honest about uncertainty.** Promoting an edit to user review
  is a feature, not a failure.
- **Be aggressive about Step 1 (proper noun audit).** This is where
  the first pass most often falls short. Spending 30% of your
  attention here is the right allocation.
