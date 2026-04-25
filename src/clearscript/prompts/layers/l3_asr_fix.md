# L3: ASR Error Correction (word-level)

Fix transcription errors at the word/term level. Match against the user's terminology library first; only fall back to context-based inference when no library match exists.

## Common ASR error categories

| Type | Example | Basis for fix |
|---|---|---|
| Pro term mis-transcribe | spoken "skip level" → ASR wrote "scalable" | management/tech context |
| Homophone substitute | 技术项 → 技术向 | spoken collocation |
| Extra/missing characters | 接在10% → 在10% | grammatical flow |
| Acronym mis-transcribe | spoken "GEO" → ASR wrote "GRU" | semantic context |
| Company name | DeFi → Dify, Minus → Manus | known company library |
| Same person multiple spellings | 阿丽 / 安丽 / 艾迪 → Eileen | speaker unification |
| Number-string-as-date | 53531 → 2026-05-31 | ASR reads dates as digit runs |
| Confused acronyms | SOG → SLG, EAT → E-E-A-T | industry context |
| Product/tech names | Dust Script → JavaScript | tech background |
| Chinese nickname → formal | 四七 → Siqi | context + user confirmation |

## Principle: don't over-correct spoken style

Keep colloquialisms. Examples to **preserve**:

- 蛮好的 (don't change to 很好)
- 做事情 (don't change to 做事)
- "差不多三四百人" (don't standardize to "约 350 人")
- "you know" / "I mean" / "怎么说呢" — leave 1-2 per paragraph for naturalness

The original voice is part of the value. L3 fixes ASR mistakes, not speaker style.

## Data integrity check

When the speaker mentions money, percentages, headcount, timelines, ARR, prices — **cross-check across the chunk for internal consistency**. Flag inconsistencies for the user to resolve in Stage 7 batch-ask. Do not silently pick one value.

## When library and context disagree

Library wins. The library represents user-confirmed knowledge. If your context inference contradicts the library, log a `needs_user_review` entry rather than override the library.
