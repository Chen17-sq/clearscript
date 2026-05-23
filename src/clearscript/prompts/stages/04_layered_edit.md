# Stage 4: Layered Edit

This is the core editing stage. You will receive a chunk of raw ASR
transcript along with:

- The Context Briefing answers
- Relevant terminology library entries (pre-loaded based on the briefing)
- All seven layer specifications (L1, L2, L3, L3.5, L4, L5, L6)

## Step 0 — Orient before editing (mandatory)

Before applying any layer, read the chunk once and form a mental model:

1. **What domain is this transcript about?** (VC ref check / founder
   interview / podcast / customer interview / board meeting / academic
   discussion / ML research / hardware design / etc.) The domain
   controls how aggressively you correct proper nouns in L3 — an unknown
   English token in an AI-infra conversation is a probable mis-heard
   company name; the same token in a HR conversation is probably a
   person's name. **Wrong domain inference is the #1 cause of L3
   missing real ASR errors.**

2. **Who's talking, and what are they doing?** Identify interviewer
   vs. interviewee, host vs. guest, founder vs. investor. Note any
   self-introductions ("I'm X, I work at Y"). This makes L1 nearly
   mechanical and helps L3 disambiguate person-name mentions.

3. **What are the recurring named entities in this chunk?** Make a
   short mental list of the companies, products, people, and
   technologies that come up multiple times. These are the things that
   MUST be transcribed consistently — every ASR variant of the same
   entity needs to collapse to one canonical.

4. **What's the speaker's domain vocabulary?** If they keep saying
   "agent" and "tool use" and "RAG", you're in AI-agent land. If they
   keep saying "tape-out" and "yield", you're in semiconductors. Bias
   all L3 inferences toward this vocabulary.

You don't have to write the Step-0 analysis as output — but if you
skip it mentally, L1 will mis-attribute speakers and L3 will leave
20% of the proper-noun errors in place. Do it.

## Now apply the layers

Apply the layers **in order, one at a time, across the entire chunk**.
Do not interleave layers. Finish L1 across the whole chunk, then L2,
etc.

## Layer summary

| Layer | Purpose |
|---|---|
| L1 | Speaker identity normalization |
| L2 | Head/tail trimming (pleasantries, AI summaries, farewells) |
| L3 | ASR error correction (word-level) |
| L3.5 | Sentence-level reasoning cleanup (broken syntax, stutters, garbled order) |
| L4 | Information preservation (no summarization, language fidelity, numerical specificity) |
| L5 | Dialogue structure formatting |
| L6 | Punctuation normalization |

The detailed rules for each layer are loaded from `layers/l*.md` and provided alongside this prompt.

## Output format

Return THREE sections, separated by JSON delimiter lines `---CHANGELOG---` and `---SUGGESTIONS---`:

1. **The edited markdown transcript** (above the first delimiter)
2. **A JSON change log** (between the delimiters) listing every meaningful edit
3. **A JSON list of library suggestions** (after the second delimiter) — entries you think the user should add to their terminology library so the next session is sharper. Empty list `[]` if none.

Example layout:

```
<edited markdown here>

---CHANGELOG---
[ ...changes... ]

---SUGGESTIONS---
[ ...suggested library additions... ]
```

The change log entries look like this:

```json
[
  {
    "layer": "L1",
    "old": "[Speaker 2]",
    "new": "Siqi:",
    "reason": "matched user briefing speaker map",
    "confidence": 1.0
  },
  {
    "layer": "L3",
    "old": "MAM-9",
    "new": "Mem9",
    "reason": "library exact match (asr-corrections)",
    "confidence": 0.99
  },
  {
    "layer": "L3.5",
    "old": "我们我们当时",
    "new": "我们当时",
    "reason": "stutter dedup",
    "confidence": 0.95
  },
  {
    "layer": "L3.5",
    "old": "技术他做的",
    "new": "[词序疑似错乱: 技术他做的]",
    "reason": "garbled order, refused auto-fix per anti-hallucination rule",
    "confidence": 0.6,
    "needs_user_review": true
  }
]
```

The library-suggestion entries look like this:

```json
[
  {
    "kind": "term",
    "canonical": "PingCAP",
    "type": "company",
    "domain": "ai-infra",
    "aliases_seen": ["PinkCup", "PingCup"],
    "rationale": "Database company referenced multiple times; ASR consistently mishears the name."
  },
  {
    "kind": "speaker",
    "canonical_name": "Eileen",
    "display_label": "Eileen：",
    "aliases_seen": ["Speaker 2", "阿丽"],
    "rationale": "User briefing introduced as the founder; recurring across turns."
  },
  {
    "kind": "edit_pattern",
    "title": "Preserve approximate-number phrasing",
    "trigger_desc": "When the speaker says ranges like '差不多三四百人'",
    "action": "Keep the original phrasing; do not standardize to a single precise number.",
    "rationale": "Approximate phrasing carries the speaker's uncertainty signal."
  }
]
```

Suggestion rules:

- **Only suggest things you saw in this chunk.** No generic industry knowledge.
- **Skip if already in the provided library context.** Don't propose duplicates.
- **Be conservative.** Better to suggest 3 high-quality entries than 30 noisy ones.
- **`kind` must be one of**: `term`, `speaker`, `edit_pattern`.

## Discipline

- **Never silently rewrite for fluency.** If a sentence is broken, either fix it with high confidence (and log) or flag it (and refuse to fix).
- **Every edit must appear in the change log.** Trivial whitespace cleanup excepted.
- **Track uncertainties separately.** Items with `needs_user_review: true` will be batched for the user in Stage 7.
- **Do not modify the original speaker order or question/answer sequence.**
- **Always emit all three sections**, even if changelog or suggestions are empty (use `[]`).
