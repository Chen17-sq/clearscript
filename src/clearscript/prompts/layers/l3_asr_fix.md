# L3: ASR Error Correction (word-level)

This is the most cognitively demanding layer. The user is **paying you for
associative reasoning**, not literal transcription. ASR tools mangle every
proper noun and most domain jargon. A literal transcript that leaves
"Tabby" / "Minus" / "iShopee" intact is no better than ChatGPT — and the
user can already run ChatGPT.

Your job at L3: **catch every recoverable ASR error**, even ones that
require context-aware reasoning. Library matches are the easy wins;
context-driven inference is the actual value.

## How to do L3 (mandatory routine)

Before writing any output, walk through this sequence:

### Step 1 — Identify the domain

Read the chunk once. Ask: what topic is being discussed?

Examples of inferences:
- Mentions of "founder / 融资 / 估值 / 投资" → **VC / startup interview**
- Mentions of "RAG / embedding / vector DB / agent / LLM / inference" → **AI infrastructure**
- Mentions of "GPU / FLOPs / scaling laws / pre-training" → **foundation models / ML research**
- Mentions of "具身 / robot / VLA / embodied / 机器人" → **embodied AI / robotics**
- Mentions of "RL / reward model / RLHF / PPO" → **RL research**
- Mentions of "PMF / SLG / GTM / ARR / churn" → **growth / GTM**
- Mentions of "tape-out / 流片 / chiplet / EDA" → **semiconductors**
- Mentions of "diffusion / NeRF / 3D" → **generative media / 3D**

Once you've identified the domain, **proper nouns must be interpreted
within that domain.** A weird mid-sentence English noun in an AI infra
conversation is overwhelmingly likely to be a misheard AI infra company
name — not random English.

### Step 2 — Scan for ASR-suspicious tokens

These patterns are red flags. Mark every one for closer look:

- **Capitalized English in Chinese sentences** that don't quite look like
  real words: `iShopee`, `Tabby`, `Minus`, `DeFi`, `OpenCloud`, `Tably`,
  `Dust Script`, `Difan`, `PinkCup`, `Nubians`, `Aeexa`
- **CamelCase or weird casing**: `OpenClod`, `BaiTu`, `PingCop`
- **Numbers-as-letters**: `MAM-9`, `M3M`, `Mem九`, `X3`, `S2`
- **Acronyms whose expansion seems off for the domain**: `GRU` in a VC
  context (probably `GEO`); `SOG` mid-go-to-market chat (probably `SLG`);
  `EAT` mid-SEO chat (probably `E-E-A-T`)
- **Person names that don't follow standard Chinese / English patterns**:
  three-character "names" with weird tonal mix, English first names with
  no last name in a context that needs disambiguation
- **Mid-sentence proper nouns that break topic flow**: speaker discussing
  AI agents, suddenly says "Minus" — that's `Manus`, not Latin

### Step 3 — Cross-reference the library

For every suspicious token from Step 2:

1. **Library hit?** Look up the token in the supplied library context
   (canonical names AND aliases). Apply the correction. Done.
2. **Library miss but high-confidence inference?** Use your world
   knowledge of well-known companies / products / people in the domain
   you identified in Step 1. If you have ≥75% confidence that a real
   entity matches the ASR output phonetically and fits the topic, apply
   the correction. **And add it to SUGGESTIONS** so it lands in the
   library for next time.
3. **Library miss + ambiguous?** Apply the most likely correction with
   `confidence < 0.75` and add `needs_user_review: true`. Also add to
   SUGGESTIONS.
4. **Library miss + no plausible canonical?** Leave the token, but
   still add a SUGGESTIONS entry flagging it as "unrecognized proper
   noun, may be ASR artifact" so the user can investigate.

**Calibration for RAW ASR input**: expect 3-15 L3 corrections per minute
of transcript if the speakers used proper nouns at all. Finishing a raw
60-minute transcript with zero L3 changes almost always means you missed
errors — go back through Step 2.

**Calibration for ALREADY-CLEAN input**: if the transcript shows signs of
prior cleanup (canonical names already correct, consistent speaker labels,
no ASR artifacts — common on re-runs), **zero or near-zero L3 changes is
the correct answer**. Never invent corrections to look productive; every
change must point at a real, identifiable ASR error. An empty changelog
on clean input is success, not failure.

## Phonetic similarity patterns (Mandarin + English ASR)

ASR systems consistently confuse these. Look for them aggressively:

### Mandarin homophones / near-homophones

| ASR wrote | Speaker likely said | Common contexts |
|---|---|---|
| 技术向 ↔ 技术项 | context decides | 技术项 when itemizing project line-items; 技术向 when describing an orientation (技术向的人). Don't auto-swap — check which fits |
| 巨身 / 据身 / 居室 | 具身 | embodied AI |
| 视觉模型 | 世界模型 | only when the topic is world models, NOT vision models — check context |
| 凡demination / 弗 daun | foundation | foundation model |
| 阿尖体克 / 阿genti | agentic | AI agents |
| 阿丽 / 安丽 / 艾迪 | Eileen | speaker name (when briefing/library names an Eileen) |
| 四七 | Siqi | speaker name |

### English ASR confusions (common in code-switched Chinese transcripts)

| ASR wrote | Speaker likely said | Why |
|---|---|---|
| Tabby / Tably / Tabli | Tavily | b ↔ v swap, common with English-Chinese ASR |
| Minus / Mainus | Manus | n preserved, vowel mangled |
| DeFi / Difan / 底牌 | Dify | initial /d/ same, rest scrambled |
| iShopee | Anthropic | first syllable lost entirely (long word) |
| OpenCloud / OpenCrawl | OpenClaw | tail morpheme confusion |
| MAM-9 / 妈姆9 / Mem九 | Mem0 | number-as-Chinese character |
| Nubians | Nebius | unusual word, phonetic guess |
| PinkCup / PingCup | PingCAP | acronym partial recognition |
| X3 / Aeexa | Exa | single-syllable proper noun |
| Alexa | Exa | longer existing word eats short proper noun |
| Dust Script | JavaScript | rhythm preserved, syllables wrong |
| Braun | Brave | last consonant confusion |
| WebSphere | web search | familiar word eats unfamiliar phrase |
| double E A T | E-E-A-T | letter-by-letter reading of acronym |
| GRU | GEO | acronym hallucinated to closest known one |
| scalable | skip level | ONLY in 1-on-1/org-chart contexts (skip-level meeting); when the speaker is genuinely discussing scalability, keep `scalable` |
| SOG | SLG | letter shape similarity |
| PNF / PMS | PMF | VC acronym distortion |

### Code-switching specific failures

When a Chinese speaker drops an English word mid-sentence, ASR often
either: (a) translates phonetically into Chinese characters, or
(b) substitutes a similar-sounding English word it recognizes more.

Listen for:
- A Chinese sentence containing a SINGLE 1-3 character "word" that
  doesn't fit grammatically — it's probably a transliterated English
  proper noun. (e.g. 我们用 **底牌** 做 → 我们用 **Dify** 做)
- A Chinese sentence containing a common English word that doesn't
  match the topic (`Alexa` in a search-tool discussion → likely `Exa`)
- Numbers spoken in English embedded in Chinese ("七 hundred 二十" →
  "720" — keep as digits)

## Library context usage — read this carefully

Before each chunk, you will be supplied with a **"Term mappings from
your library"** section listing the user's confirmed aliases and
canonicals. **Treat that list as load-bearing.** Walk through it once
mentally. Then read the transcript with that list active.

If the transcript contains an alias from the list, the correction is
mandatory — confidence 0.99, no ambiguity.

If the transcript contains something that *sounds like* a library
canonical but isn't quite a listed alias, still apply the correction
and add the new alias to SUGGESTIONS so the library grows.

## Principle: don't over-correct spoken style

Keep colloquialisms. Examples to **preserve**:

- 蛮好的 (don't change to 很好)
- 做事情 (don't change to 做事)
- "差不多三四百人" (don't standardize to "约 350 人")
- "you know" / "I mean" / "怎么说呢" — leave 1-2 per paragraph for naturalness
- 嗯 / 啊 / 那个 used as floor-holders — leave some, trim only if dense

The original voice is part of the value. L3 fixes ASR mistakes, not
speaker style. The user's negative-rules list (do-not-change
overrides) takes precedence over your inferences.

## Data integrity check

When the speaker mentions money, percentages, headcount, timelines,
ARR, prices, dates — **cross-check across the chunk for internal
consistency**. Flag inconsistencies for the user to resolve in Stage 7
batch-ask. Do not silently pick one value.

Watch for ASR digit confusion specifically:
- "five three five three one" → check whether it's a number `53531` or
  a date `2025-03-15` (zero often dropped in Mandarin date narration)
- "三个人 / 三千人 / 三百人" — make sure the ASR didn't drop a 千 or 百
- Currency: confirm 万 / 亿 not lost when number is huge

## When library and context disagree

Library wins. The library represents user-confirmed knowledge. If your
context inference contradicts the library, log a `needs_user_review`
entry rather than override the library.

## The cost asymmetry: lean correct

- Missing a real ASR error → user has to manually fix it (painful, slow)
- Proposing a wrong fix → user rejects it from the change log (fast)

So when in doubt, **propose the correction with a confidence score**.
Don't silently leave a suspicious token. Either fix it or add it to
SUGGESTIONS with rationale. Silence is the wrong answer.
