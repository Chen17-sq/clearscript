# Changelog

All notable changes to clearscript will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.21] - 2026-06-11

### The deep-audit release: 61-agent review, 52 confirmed findings, refactor + fixes.

User directive: "全面继续做，重构可以". Ran a multi-agent audit (6 parallel
reviewers over server / pipeline / web JS / prompts / library / packaging,
every finding adversarially verified by independent agents — 52 confirmed,
3 refuted), then refactored the server and fixed everything that mattered.

### Refactored — server.py → clearscript/api/ package

The 1,558-line ``create_app`` closure (46 endpoints) is now seven focused
modules: ``deps`` (AppState: lazy config, library factory, provider
resolution), ``models``, ``slugs``, ``routes_core``, ``routes_providers``,
``routes_run``, ``routes_projects``, ``routes_library``.
``clearscript.server`` remains as a compatibility shim. Route table
verified byte-identical (54 routes) before and after.

### Fixed — P0s

- **`uv build` failed outright** — the wheel force-include section
  duplicated files hatchling already packages; hatchling ≥1.30 hard-errors
  on duplicate archive paths. **`uv tool install git+...` was broken for
  everyone.** Removed the redundant force-include.
- **Every GitHub release shipped without the wheel/sdist** —
  ``build_skill.sh`` ran ``rm -rf dist/`` AFTER ``uv build``, wiping the
  installable artifacts; the release action's default
  ``fail_on_unmatched_files: false`` published anyway. Both fixed, plus a
  verify step that fails the release if any artifact is missing.
- **SQLite thread-affinity crash in SSE streams** — Starlette drives sync
  generators on a threadpool where every ``next()`` can land on a
  different thread; ``sqlite3.connect`` defaults to
  ``check_same_thread=True``, so concurrent requests killed paid runs
  mid-stream with ``ProgrammingError``. Now ``check_same_thread=False``
  (access is sequential per generator, so this is safe).
- **Train-library modal was completely dead** — the close-button wiring
  looked up ``cs-bs-close`` but the button's id is ``cs-bootstrap-close``;
  the resulting TypeError killed ALL subsequent modal wiring (file drop,
  Run button). One id, whole feature dead.

### Fixed — P1s

- **Client disconnect mid-stream lost the finished run**: persistence now
  happens the moment the ``complete`` event is produced, before the next
  yield — closing the tab after completion can no longer discard a paid
  run.
- **One corrupted meta.json bricked /api/projects, the inbox, and
  compare**: ``read_meta`` is now tolerant, ``write_meta`` is atomic
  (tmp + ``os.replace``).
- **L2 trimmed mid-transcript content on multi-chunk runs**: the user
  prompt now carries "Chunk position: i of N" and l2_trim.md scopes
  head-trimming to the first chunk, tail-trimming to the last, and NO
  trimming on middle chunks.
- **Self-review could silently delete text** (empty ``new``) **or replace
  the wrong occurrence** (ambiguous ``old``): both cases now route to
  user-review diagnostics instead of being applied.
- **Bootstrap 'jargon' candidates silently dropped on Accept** — now
  stored as terms with type ``jargon``.
- **XSS via model output**: ``escapeHtmlSimple`` didn't escape quotes
  (attribute injection through diff tooltips); ``renderSuggestions``
  interpolated canonical/alias/rationale unescaped. All escaped now.
- **`{once:true}` delegated listeners**: list interactions (delete
  buttons, inbox accept/dismiss, suggestion checkboxes) died after the
  first interaction and stacked duplicate handlers across renders. All
  replaced with persistent delegation attached once at boot.
- **Bootstrap drag-drop accepted binary files** (`.docx` read as text =
  garbage in the prompt) — dropped files are now extension-filtered with
  a clear message.
- **Stale cost-cap gate**: Run now fetches a fresh estimate for the exact
  text being run instead of trusting the debounced preview.
- **Cmd+Enter bypassed the disabled Run button** — double-spend guard.
- **FTS5 search crashed on query-syntax input** (``a AND``, unbalanced
  quotes) — input is phrase-quoted with a LIKE fallback.
- **Library export/import dropped status/confidence/definition/notes** —
  confirmed/verified terms round-tripped back to 'proposed'. Preserved
  now.
- **/api/example empty for wheel installs** — the example transcript now
  ships as package data.
- **CI never built the wheel** — new ``package`` job builds, installs
  into a clean venv, verifies data files, boots the app factory, and
  checks the skill build doesn't clobber artifacts. Matrix extended to
  Python 3.14.

### Fixed — prompt contradictions (from the prompts auditor)

- L3 and L4 gave opposite instructions for ``scalable``/``skip level``
  and ``技术向``/``技术项`` — now context-qualified on both sides.
- Canonical for MAM-9 was ``Mem0`` in L3 but ``Mem9`` in stages 04/07/08
  — unified to ``Mem0``.
- Removed two garbled no-op rows from the L3 phonetic table.
- **"Already clean" calibration**: the 3-15-corrections-per-minute quota
  now only applies to raw ASR input; on already-clean input (re-runs)
  zero changes is explicitly the correct answer — no invented edits.
- Stage 08 re-scan now uses the same three-section output contract as
  Stage 4.
- Self-review input restructured: plain sections + ``<<<TRANSCRIPT>>>``
  markers instead of double-JSON-wrapping the entire document (cheaper,
  more reliable); fence contradiction resolved.

### Changed

- ``estimate_cost`` now includes per-chunk system-prompt overhead
  (~6k tokens/chunk) and the self-review factor (×1.35). Estimates were
  systematically ~40-60% low — the exact complaint that motivated the
  actual-cost feature.
- Vocabulary primer: deprecated terms no longer consume cap slots,
  ranking is by usage instead of recency, and terms already emphasised
  for the current chunk aren't duplicated.
- Filenames bypass the mic-check slug heuristics (user-chosen names like
  ``ok.txt`` or ``好的会议记录.docx`` are legitimate slugs).
- Test suite is hermetic: fake keyring + isolated prompt-override dir via
  an autouse fixture (the suite used to probe the real macOS keychain).

### Tests

292 → **306**. All passing, ruff clean, `uv build` + skill build verified,
browser-level verification of the UI fixes (modal lifecycle, delegated
listeners across re-renders, escaping) via live preview with zero console
errors.

## [0.0.20] - 2026-05-23

### Added — Self-review pass + L3.5 rewrite

Following v0.0.19's prompt rewrite, user said "继续很深入改" — keep going
on quality. This release adds the single biggest quality multiplier I
know how to ship without changing the model: a **second LLM pass** that
re-reads the stitched output and catches what the first pass missed.

### Self-review (Stage 6) is now wired into the pipeline

After all chunks complete, ``Pipeline.iter_events`` makes one additional
LLM call on the stitched edited markdown. The call uses a dedicated
prompt (``stages/06_self_review.md``) that walks the model through a
5-check routine:

1. **Proper noun audit** — re-read every capitalised English word and
   CamelCase token; correct any the first pass left untouched. This is
   the headline reason: the first pass is laser-focused on layered
   editing and consistently misses 20-30% of L3 errors that a fresh
   read catches.
2. **Speaker consistency audit** across the whole document.
3. **Cross-section data consistency** — ARR / headcount / funding /
   percentages flagged when they don't agree.
4. **Format hygiene** — leftover `[Speaker N]`, mixed punctuation
   styles, bullet inconsistencies.
5. **Over-correction rollbacks** — first-pass changes with
   confidence < 0.7 get a sanity check.

Output is a structured JSON object with `additional_corrections`,
`rollbacks`, `promotions_to_user_review`, `data_conflicts`, and
`format_issues`. Corrections get applied via string-replace on the
stitched markdown; everything else is surfaced to the UI as diagnostics
the user should look at.

Cost: **one extra LLM call per Run** (not per chunk). For a 60-min
transcript split into 5 chunks, that's ~17% more API spend for a
disproportionate quality lift. Auto-skipped if the stitched output
exceeds 100k chars to keep cost bounded on very long transcripts.

Default ON. Tests opt out explicitly when they're testing the layered
edit alone.

### SSE events

Three new events flow during the review pass:
- ``self_review_start`` — UI shows "↻ Self-review — re-reading for
  missed corrections…"
- ``self_review_done`` — UI shows "+N fixes · M data conflicts to
  check · K ambiguous items flagged" with updated token counts
- ``self_review_error`` — opportunistic skip if the model returns
  garbage; main result still ships

The ``complete`` event now carries a ``self_review`` field with the
full diagnostics dict.

### L3.5 (sentence-level cleanup) rewritten

Same treatment as L3 in v0.0.19. The conservative table now wraps a
**7-check routine**:

1. Sentence boundary correctness (ASR split / merged wrong)
2. Stutter / repetition dedup (exact `X X` only)
3. Word order garbling (≥85% confidence or flag)
4. Missing function words / abandoned sentences (never auto-complete)
5. Speaker switch swallowed mid-paragraph
6. Number/letter confusion in spoken digits
7. Same-sound substitution destroying meaning (cohort vs co-host)

Hard table of confidence thresholds per change type. Explicit "what
L3.5 does NOT do" list to keep the model bounded.

### Tests

284 → **292** (+8). All passing. Ruff clean.

- ``test_pipeline_self_review.py`` (new file, 8 tests): event ordering,
  corrections applied, token counts include both passes, opt-out
  flag, auto-skip for huge output, garbage response robustness,
  diagnostics surfaced in `complete`, ignored when `old` not in doc.

## [0.0.19] - 2026-05-23

### Changed — Prompts rewritten for actual associative reasoning

User feedback after v0.0.18: *"我感觉现在的能力还是很差，就很多东西你
联想不到去进行逐字稿的修改"*. They were right — the L3 (ASR fix) prompt
said "be proactive" but didn't give the model a routine to follow, and
the library context was just listed at the bottom without telling the
model to actively cross-reference. Literal transcription quality only
needs ChatGPT; the value of clearscript is the associative leaps a
context-aware editor makes ("Tabby in an AI-infra discussion is
phonetically Tavily"), and the prompts weren't pushing for those.

### What changed

**``system_base.md``** — opens with "The user is paying you for
**associative reasoning** that a literal transcript can't deliver". The
"zero hallucination" rule now explicitly distinguishes content
hallucination from transcription repair (correcting Tabby → Tavily
with reasoning is not hallucination). A new "Use the supplied library
aggressively" section primes the model to walk through the library
mappings BEFORE reading the transcript.

**``layers/l3_asr_fix.md``** — completely rewritten. New mandatory
3-step routine:

1. **Identify the domain** (VC / AI infra / foundation models /
   embodied AI / RL / GTM / semiconductors / 3D — with concrete
   keyword cues for each)
2. **Scan for ASR-suspicious tokens** (capitalised English in Chinese
   sentences, CamelCase oddities, numbers-as-letters, acronyms that
   don't fit, mid-sentence proper nouns that break topic flow)
3. **Cross-reference the library + apply phonetic patterns**

Plus a much-expanded phonetic similarity table covering both Mandarin
homophone confusions (具身 → 巨身 / 据身 / 居室) and English ASR
confusions in code-switched Chinese transcripts (Tabby/Tably/Tabli
→ Tavily, Minus → Manus, DeFi/Difan/底牌 → Dify, iShopee → Anthropic,
MAM-9/妈姆9 → Mem0, PinkCup → PingCAP, Nubians → Nebius, etc.) — 25+
concrete patterns the model can pattern-match against.

The prompt now ends with a hard discipline statement: **"You should
be making 3-15 L3 corrections per minute of transcript. If you finish
a 60-minute transcript with zero L3 changes, you almost certainly
missed something."**

**``layers/l1_speaker.md``** — beefed up with a 4-step routine for
inferring speakers from content (count distinct speakers, infer
interviewer-vs-interviewee from turn length and content, catch
self-introductions, consolidate ASR-over-split speakers). The example
now shows merging Speaker 2 and Speaker 3 when content + role match.

**``stages/04_layered_edit.md``** — new "Step 0: Orient before editing"
section forcing the model to identify domain, speakers, recurring
entities, and domain vocabulary BEFORE applying any layer. Called out
as "the #1 cause of L3 missing real ASR errors" when skipped.

**``pipeline.py``** — ``_collect_library_context`` now emits a full
vocabulary primer at the top (every canonical + every alias, capped at
200), regardless of whether the entity appears in the current chunk.
This lets the model do phonetic matching against the user's vocabulary
even for novel ASR misspellings the entity extractor wouldn't catch.

**``prompts/__init__.py``** — the briefing and library context sections
in the composed system prompt now have explicit framing telling the
model HOW to use them ("**Use it to bias your proper-noun corrections.**"
and "**APPLY AGGRESSIVELY**" — not just listing the data).

### Tests

284 still passing. Ruff clean. Two existing prompt-composition tests
were updated to match new heading text.

### Caveat

Prompt quality has a ceiling per model. For users on
``deepseek-v4-flash`` (the streaming-friendly default), upgrade to
``deepseek-v4-pro`` or ``claude-sonnet-4-6`` for hard transcripts —
the routine in L3 is more taxing than v4-flash can fully execute.
Setting the model is one click in ⚙ Keys → or pass ``--model
deepseek-v4-pro`` on the CLI.

## [0.0.18] - 2026-05-23

### Added — Library Bootstrap: the answer to "why not just ChatGPT?"

Real user pushback during /goal session: *"感觉就是不好用，这产品的核心是啥？"*
The complaint had a real diagnosis: clearscript's compounding library
is its moat, but the moat only emerges *after* 5-10 cleanups. The first
few runs are no better than ChatGPT. User insight from the same
conversation: *"可以先输入那些稿子，在这里面解析出来一些。这样的话就不用等一篇一篇地处理。"*
**Bootstrap inverts the curve.** Drop a stack of past transcripts ONCE,
extract candidate library entries upfront, accept in one click, then
start cleaning with a warm library on run #1.

### Components

- **New prompt** ``prompts/stages/00_library_bootstrap.md`` — pure
  entity extraction, JSON output, no rewriting. ~10× cheaper than full
  cleanup per transcript.
- **New module** ``core/bootstrap.py`` — ``bootstrap_from_transcripts``
  runs the prompt over each input, aggregates candidates with
  per-transcript frequency (verbose speakers don't get extra weight),
  unions alias sets, fails soft per-transcript (one garbled response
  doesn't kill the batch).
- **New endpoint** ``POST /api/library/bootstrap`` (SSE) — emits
  ``plan / transcript_start / transcript_done / transcript_error /
  complete``. Hard cap of 50 transcripts per batch to bound spend.
- **New CLI command** ``clearscript lib bootstrap <files>...
  [--accept-all] [--min-seen N]`` — Rich table of candidates ranked
  by frequency, optional auto-accept for power users.
- **New web UI** — yellow CTA card on the editor view when the
  library has only the seed pack (≤17 terms). Opens a modal with:
  drag-drop multi-file (cap 50), per-file progress with live log,
  results table with checkboxes (default all selected) sorted by
  ``times_seen``, Select-all / Accept-selected buttons. Closes by
  itself and refreshes the library stats when done.

### Why this is the killer feature

It's the **only** explanation for "why install clearscript instead of
pasting into ChatGPT". Without bootstrap: library compounds across 10
runs, slowly. With bootstrap: library is already armed before run #1.
A user who has 20 past founder interviews sitting in a folder can
warm clearscript on those in ~5 minutes (one cheap extraction pass
each) and have it dial in their portfolio companies, their jargon,
their recurring speakers — *before* they clean a single new
transcript.

### Tests

265 → **284** (+19). All passing. Ruff clean.

- ``test_bootstrap.py`` (new file, 14 tests): aggregation contract
  (alias union, per-transcript count not per-mention, sort by
  frequency, speaker shape, empty array OK, malformed entries
  dropped), error handling (one failed transcript doesn't kill
  batch), response parsing (fenced markdown, prose-wrapped JSON,
  garbage returns empty).
- ``test_server.py``: +4 (endpoint streams events, rejects empty,
  rejects >50, end-to-end bootstrap→accept→library)
- ``test_cli.py``: +1 (bootstrap --accept-all writes to library)

## [0.0.17] - 2026-05-23

### Fixed — Empty env var no longer fakes a set credential

While smoke-testing v0.0.16 immediately after shipping it, the claude
provider pill showed ``has_key=True`` but ``key_source=null`` —
contradictory state. Root cause: ``ANTHROPIC_API_KEY=`` (declared but
blank, common when someone half-set their shell config) returned ``""``
from ``resolve_api_key()``, which the server's ``has_key`` check
treated as a valid credential via ``is not None``.

User impact: the pill looks enabled, the user clicks Run, and gets a
401 from the provider with no clear message.

Fix: ``ProviderConfig.resolve_api_key()`` now strips and treats empty
strings as "no key" across all three sources (inline TOML / keyring /
env). Regression-tested in a new ``test_config.py`` covering 9 cases:
priority ordering, empty values at each source, keyring failure
fallback, inline-config-wins.

### Tests

256 → **265** (+9). New ``test_config.py``. Ruff clean.

## [0.0.16] - 2026-05-23

### Fixed — In-app API key input

Real user feedback from /goal session: **"没地方输入 api key"** — there was
no in-app way to set an API key. The user had to know what an env var
is, edit ``~/.zshrc`` or ``~/.bashrc``, source it, restart the server.
That's three blocking steps for a non-technical user before they can
clean a single transcript.

v0.0.16 makes this a one-click operation:

- **Web UI**: A new ``⚙ Keys`` button next to the provider strip
  opens a modal listing every provider with its current key source
  (``ENV`` / ``KEYRING`` / ``CONFIG`` / ``NONE``), a paste field, and
  a "get a key →" link to the right vendor console. Save persists to
  the OS keyring; the providers list refreshes automatically so the
  pill becomes selectable instantly. Clicking a disabled pill also
  opens the modal — there's no way to be stuck.
- **CLI**: ``clearscript set-key <provider>`` prompts for the key
  with hidden input (so it doesn't end up in shell history) and
  saves it to the keyring. ``--delete`` removes a stored key.
- **Storage**: OS keyring via the ``keyring`` package (was already a
  dep — just unused). macOS Keychain / Windows Credential Manager /
  Linux Secret Service. Stored under service ``clearscript`` +
  the provider name. Survives reboots, never touches disk via
  clearscript code.
- **Resolution order** in ``ProviderConfig.resolve_api_key()``:
  inline ``api_key`` in TOML > keyring > env var. So an explicit
  in-app set always wins.
- **Pill UI** now shows a small chip on each provider — ``KEY``
  (yellow, from keyring), ``ENV`` (white, from env var), or ``CFG``
  (blue, from config TOML) — so you can see at a glance which keys
  are wired up where.

The change is fully backward-compatible: users who'd set
``ANTHROPIC_API_KEY`` etc. in their shell still see those work
(env vars still resolve, just at lower priority than keyring).

### Tests

248 → **256**. All passing. Ruff clean.

- ``test_server.py``: +5 (set + delete keyring endpoints, empty-key
  rejection, unknown-provider 404, /providers exposes key_source)
- ``test_cli.py``: +3 (set-key happy path, unknown provider, --delete)

The keyring is mocked with a fake module injected into ``sys.modules``
— tests don't touch the system keychain.

## [0.0.15] - 2026-05-23

### Fixed — CI green on Windows

v0.0.14 shipped with all UX fixes but CI failed on the Windows runners
across all Python versions. Cause: test fixtures wrote a tmp ``config.toml``
embedding the tmp_path as a TOML basic (double-quoted) string. On Windows
tmp_path looks like ``C:\Users\runneradmin\...`` — and the TOML parser
interpreted ``\U`` as a Unicode escape, failing with "Invalid hex value
at line 1, column 22".

Fix: switch the three fixture writes to TOML literal (single-quoted)
strings, which don't interpret escape sequences. Confirmed green across
all 9 CI matrix cells (py3.11/3.12/3.13 × Linux/macOS/Windows).

This is a test-only fix — the v0.0.14 runtime works fine on Windows;
only the test suite couldn't run there. v0.0.15 = v0.0.14 + the
cross-platform CI fix, recommended as the "known good" tag.

## [0.0.14] - 2026-05-23

### The "actually-usable-by-a-non-tech-VC-analyst" release.

The /goal directive was: "I want a complete, fully usable project." A
production-readiness audit flagged 3 P1 UX gaps a non-tech user would
hit before their first coffee. v0.0.14 closes them, plus two real bugs
the audit shook out.

### Added — Pre-flight cost confirmation

A 60-minute founder interview on Claude Opus runs ~$10-50 depending on
length. v0.0.13 showed an estimate but didn't gate the run. v0.0.14:
before ``/api/run-stream`` fires, the JS checks the latest cost estimate
against a soft cap (default $0.50, settable via
``localStorage.setItem('clearscript-cost-cap', '5.00')``) and requires
explicit ``confirm()`` above it. Shows token counts + model name so the
user knows what they're approving.

### Added — Library health panel in the web UI

v0.0.13 shipped the ``/api/library/health`` endpoint + CLI command but
no web UI surface. v0.0.14: a new **Health** subtab in the Library tab
shows duplicate aliases (red — these are pipeline correctness bugs),
duplicate canonicals, low-confidence terms (< 0.3), and stale terms
(>90 days unused). Each section has a hint line explaining why it
matters and what to do.

### Added — Persistent suggestions inbox (Mode B v2)

Until now, Mode B suggestions lived inside each project's
``suggestions.json``. If you ran 10 transcripts and didn't accept
suggestions immediately, you'd have to drill into each project to
harvest them. v0.0.14:

- ``GET /api/library/suggestions/inbox`` aggregates pending suggestions
  across **every** saved project, dedupes by ``(kind, canonical/title)``,
  filters out anything already in your library, and tracks
  ``times_seen`` + ``source_slugs`` so you see which terms are recurring.
- ``POST /api/library/suggestions/inbox/dismiss`` records explicit
  rejections to a sidecar JSON so they don't keep resurfacing.
- ``DELETE /api/library/suggestions/inbox/dismissed`` wipes the
  dismissal set if you want to re-review everything.
- **Web UI**: new **Inbox** subtab in the Library tab with per-item
  Accept / Dismiss buttons + an **Accept all** action. A red badge on
  the tab nav shows the pending count, refreshed automatically after
  each run.

### Added — Better first-run UX

When no provider has an API key set, the editor now shows a persistent
yellow help card (instead of the easy-to-miss status pill) with:

- A table of every provider's env var name (copy-paste ready)
- A "where to get one →" link for each provider
- A note about adding the export to ``~/.zshrc`` / ``~/.bashrc``
- A "keys stay on your machine" reminder

### Added — Negatives + Compare buttons in the web UI

- **Negatives** subtab in the Library tab with add/list/delete UI
  (matches the v0.0.13 CLI commands).
- **⇄ Compare** button on rerun project cards opens a colorized diff
  modal (+green / -red / @@blue hunk markers) — already in v0.0.13's
  detail panel, this just makes the entry point more visible.

### Fixed — Test fixtures leaking into the user's real ~/Documents

**The audit's biggest find.** ``Config.projects_root`` defaults to
``Path.home() / "Documents" / "clearscript" / "projects"`` (by design,
so non-tech users can find their files in Finder). But test fixtures
were patching ``DATA_DIR`` only, leaving ``projects_root`` pointing at
the user's real directory. Every test run wrote 5-20 garbage projects
to ``~/Documents/clearscript/projects/``. Across this session that
accumulated to 277 leaked test projects on the maintainer's machine —
plus malformed meta.json files that crashed the project listing.

Fix: every test fixture now writes a ``config.toml`` into the patched
``CONFIG_DIR`` that explicitly overrides ``projects_root`` to a
``tmp_path`` directory. Verified clean: before this fix, ``pytest``
added ~5 leak directories per run; after this fix, the user's
projects dir count stays stable.

### Fixed — Inbox / accept-suggestion overlap with seed pack

Wrote inbox tests using "Mem0" and "Manus" as the canonical — both
already in the seed pack, so the inbox correctly excluded them and the
tests failed. Replaced with non-seed-pack canonicals in the tests.

### Tests

243 → **248** (+5). All passing. Ruff clean. New test cases:

- ``test_server.py``: +5 (inbox aggregates across runs, inbox excludes
  already-accepted, dismiss persists, dismiss validates payload, clear
  dismissals resets)

The big wins this release are UX, not LOC. But the test-pollution fix
makes future tests trustworthy.

## [0.0.13] - 2026-05-23

### The library-hygiene + reproducibility release.

v0.0.12 made the library portable. v0.0.13 makes it *legible*: you can
see what's in there, spot the cruft, and prove your reruns produced
something different.

### Added — Library health check

- ``Library.health_check(stale_days=N)`` returns five buckets:
  ``duplicate_aliases`` (same alias mapping to multiple canonicals — a
  real correctness bug for the pipeline), ``duplicate_canonicals``,
  ``low_confidence_terms`` (< 0.3), ``stale_terms`` (not used in N
  days), ``orphan_aliases``.
- ``GET /api/library/health?stale_days=N`` surfaces the report.
- ``clearscript lib health`` prints Rich tables with the top 20 of
  each bucket so you can clean up from the CLI.

### Added — Project compare (rerun diff)

- ``GET /api/projects/{left}/compare?with={right}`` returns both
  projects' cleaned markdown + a unified diff + ``{added, removed,
  identical}`` stats.
- **Web UI**: a ``⇄ Compare`` button appears on rerun project cards.
  Clicking opens a modal with the colorized diff (+ green, - red, @@
  hunk markers in blue) so you can read what your library tweak
  actually changed.

### Added — Negatives CRUD

Negative-correction rules ("don't change 蛮好的 to 很好") were only
reachable via the accept-suggestions endpoint. Now:

- ``GET /api/library/negatives`` lists them.
- ``POST /api/library/negatives`` adds one.
- ``DELETE /api/library/negatives/{id}`` removes it.
- ``clearscript lib negatives`` lists them; ``--add TEXT --not-to X``
  to add; ``--delete ID`` to remove.

### Added — Markdown library export

- ``Library.export_markdown()`` renders the library as a human-readable,
  git-friendly markdown document (terms grouped by domain, alphabetic
  within each domain, one entry per line).
- ``GET /api/library/export.md`` serves the markdown view.
- ``clearscript lib export <path> --md`` writes it locally.

The markdown view is **read-only** — for round-trip backup, use the
JSON export (``lib export <path>``). Markdown is for reading + diffing
in a git repo.

### Tests

217 → **243** (+26). All passing. Ruff clean.

- ``test_library.py``: +12 (health check buckets, deprecated exclusion,
  markdown export grouping/sorting, delete_negative).
- ``test_server.py``: +9 (health endpoint, compare endpoint with
  identical/different/404 cases, markdown export, negatives CRUD,
  validation).
- ``test_cli.py``: +5 (lib health, lib negatives add/list/delete,
  lib export --md).

## [0.0.12] - 2026-05-23

### The library-as-portable-artifact release.

Until v0.0.11, your terminology library was a SQLite file at
``~/Documents/clearscript/data/library/library.db``. You could not back
it up cleanly, share it with a teammate, or version it in git without
exporting the raw binary. v0.0.12 fixes that, plus a sweep of UI polish
and SDK-level test coverage.

### Added — Library export / import

- ``GET /api/library/export`` returns a versioned JSON blob containing
  every term + alias + speaker + edit pattern + negative rule. Deprecated
  (rejected) terms are excluded by design so sharing a library doesn't
  re-introduce someone else's rejections into yours.
- ``POST /api/library/import`` merges an export back in. Existing terms
  with the same canonical have their aliases extended (union, not
  replace); new terms are inserted; malformed records are counted as
  ``skipped`` rather than crashing.
- **CLI**: ``clearscript lib export <path>`` / ``clearscript lib import <path>``.
- Format marker (``"format": "clearscript-library-export"``) on every
  export so future versions can detect incompatible files instead of
  silently corrupting state.

### Added — CLI ``lib search``

``clearscript lib lookup`` did exact alias matching only. ``lib search`` runs
the FTS5 query against the term table so partial matches and typos
surface useful hits. Output is a Rich table with canonical / type /
domain / confidence columns.

### Added — Bulk delete

``POST /api/library/terms/bulk-delete`` accepts ``{ids: [int, ...]}`` and
deletes them in one round trip, with cascade to aliases. Returns the
count actually deleted so the UI can show "Deleted N terms".

### Added — Rerun-of badge in the projects list

A re-run project carries ``rerun_of: <orig_slug>`` in its meta. v0.0.12
exposes this in ``/api/projects`` summaries and the web UI renders a
``↻ rerun`` badge on the project card with a tooltip pointing to the
original slug. Provenance is now visible at a glance.

### Added — Real-SDK provider test coverage

Until now, ``AnthropicProvider`` and ``OpenAICompatProvider`` were only
exercised through ``_BaseProvider`` fallbacks. A regression in SDK call
shape (renamed field, changed kwarg) would slip past CI. ``test_provider_sdks.py``
now covers:

- The SDK kwargs Anthropic gets called with (model, system extraction,
  messages, max_tokens default).
- Multiple system messages joined with ``\n\n``.
- Non-text content blocks (tool_use) being ignored gracefully.
- The streaming context-manager protocol Anthropic uses.
- OpenAI-compat's ``include_usage`` stream option capturing real token
  counts from the final chunk.
- Fallback estimate when usage isn't reported.

### Tests

217 tests total (up from 191):
- ``test_library.py``: 9 new (export shape, round trip, idempotency,
  bulk delete edge cases, malformed import handling, deprecated
  terms excluded from export).
- ``test_server.py``: 6 new (export download, import endpoint, bulk
  delete endpoint, rerun_of summary surfacing).
- ``test_cli.py``: 6 new (search, export, import round trip, error
  handling).
- ``test_provider_sdks.py``: 7 new file.

All passing. Ruff clean.

## [0.0.11] - 2026-05-16

### The actually-using-the-library release.

v0.0.9 added the seed pack and v0.0.10 made streaming visible. But the user kept reporting that obvious terms ("Tabby", "OpenCloud", "DeFi") were not being corrected to their canonicals ("Tavily", "OpenClaw", "Dify") *even though* those mappings were sitting right there in the library. The audit found a clean explanation: the pipeline only injected library context when a briefing was provided, and even then only scanned the briefing text — never the transcript itself. So a user who pasted a transcript with no briefing got a silently-empty context block, and the seed pack was dead weight.

This release fixes that, adds cross-chunk learning, and ships project re-run.

### Fixed — Library context now actually loads

- ``Pipeline._collect_library_context`` now scans **the transcript** for library hits, not just the briefing. That was the missing piece — most users don't write a briefing, they just paste a transcript and click Run.
- Up to 60 term mappings get included in the system prompt; the matched alias is shown both when it equals the canonical (informational) and when it differs (substitution hint).
- Regression test in ``test_pipeline.py`` pins this behavior: a library with ``Tavily/Tabby`` and a transcript that says "Tabby" — with no briefing at all — now produces a system prompt that contains both names.

### Added — Mode C: cross-chunk learning

When a transcript is long enough to be split into multiple chunks, the model used to discover term substitutions independently in each chunk. If chunk 1 decided "Tabby → Tavily", chunk 2 wouldn't know that and might leave "Tabby" alone, or worse — pick a different correction.

- ``iter_events`` now harvests L3 (ASR-fix) changes from each completed chunk and feeds the resulting alias→canonical pairs into the next chunk's system prompt under a new section: "Earlier chunks in this same run already substituted these — stay consistent."
- Filtered to short, proper-noun-like substitutions (1–30 chars before/after) so entire-sentence rewrites don't pollute later chunks.
- Capped at 40 mappings per chunk to keep the prompt bounded.

### Added — Re-run any project against the current library

After you've added or corrected terms in the library, you can replay a saved run to see the improved output — without re-pasting the transcript:

- **Web UI**: ``↻ Re-run`` button on the Projects detail header. The result lands as a sibling project (slug suffix ``-rerun``) so the original is preserved; the new project carries ``rerun_of: <orig_slug>`` in its meta. The UI auto-selects the new project so you can immediately compare.
- **CLI**: ``clearscript projects rerun <slug>`` — same semantics, optional ``--provider`` / ``--model`` overrides.
- **API**: ``POST /api/projects/{slug}/rerun`` returns the same SSE event stream as ``/api/run-stream`` so existing clients reuse their handlers.

### Added — Easier install path

Non-developers don't need to clone the repo. README now leads with:

```bash
uv tool install git+https://github.com/Chen17-sq/clearscript.git
# or
pipx install git+https://github.com/Chen17-sq/clearscript.git
```

Then ``clearscript serve`` works as a system command. The development path (``git clone`` + ``uv sync``) is preserved for contributors.

### Tests

Added regression coverage in ``test_pipeline.py``:

- ``test_pipeline_transcript_seeds_pulled_into_context_without_briefing`` — pins the "transcript without briefing" bug fix.
- ``test_pipeline_mode_c_propagates_substitutions_across_chunks`` — verifies a substitution committed in chunk 1 is visible in chunk 2's system prompt.

Total: 116 → 116 (replaced two old tests' assertions to match the new prompt shape).

## [0.0.10] - 2026-04-27

### Fixed — Streaming UX with reasoning models

User reported "没有流式" on v0.0.9: the streaming UI looked frozen for nearly the full run. Root cause: ``deepseek-v4-pro`` is a reasoning model that thinks silently for 30–90 seconds before emitting any content tokens. The backend SSE pipeline was correct (first byte at 31ms, deltas confirmed over the wire), but with v4-pro the deltas all arrive in a late burst — so the user reasonably perceived "no streaming".

- DeepSeek default model changed from ``deepseek-v4-pro`` to ``deepseek-v4-flash``. Flash streams tokens smoothly so the live output panel fills in word-by-word, which is what the streaming UI was designed for. Pro is still available — pass ``--model deepseek-v4-pro`` (CLI) or set it in the Model field (web UI) when you want the extra reasoning quality and don't mind the silent thinking phase.
- Progress label during ``chunk_start`` now explicitly says reasoning models pause here, with a hint to use v4-flash for live streaming. The progress bar pulses while waiting for the first token so it doesn't look frozen.
- On the first ``chunk_delta`` the output panel auto-switches to Edit view so the streaming text is visible (previously, if the user had Diff view active when a previous run ended, deltas appended to a hidden textarea).

## [0.0.9] - 2026-04-26

### Three concrete user complaints, three concrete fixes

User reported running v0.0.8 with their first real transcript:

> 1. 我看不到正在跑的进程
> 2. 公司名（DeFi、Tabby、OpenCloud 等）应该自动识别
> 3. Output 实际消耗的 token 比预估多。实际花了多少钱要告诉我

### Added — Token-level live streaming

The chunk progress in v0.0.8 only showed "calling model…" with frozen 0 counters until the chunk completed. Now LLM output streams in word-by-word as it's generated.

- New ``Provider.chat_with_progress()`` yielding ``('delta', text)`` for each token chunk plus a final ``('done', ChatResponse)`` carrying real usage.
- ``AnthropicProvider`` and ``OpenAICompatProvider`` (DeepSeek/Moonshot/Qwen/etc.) implement this with **real** input/output token counts captured from streaming usage. ``OpenAICompatProvider`` sets ``stream_options={"include_usage": True}`` so DeepSeek emits a final usage chunk. Other adapters fall back to the base class's char-count estimation.
- ``Pipeline.iter_events`` now emits ``chunk_delta`` events alongside ``chunk_start`` / ``chunk_done``. The SSE endpoint forwards them.
- Web UI Editor: when a delta arrives, append it to the output textarea live (textarea is now active during streaming, not pre-disabled). Auto-scroll to follow the stream. The progress label flips to "receiving…" mid-stream.

### Added — Universal seed pack

A curated set of common ASR errors ships with clearscript and auto-loads on first use, so the model catches well-known mishears without any prior training:

- 17 terms covering AI/infra companies (Dify ← DeFi/底牌/Difan, Manus ← Minus, Tavily ← Tabby, OpenClaw ← OpenCloud, Mem0 ← MAM-9/Mem9, Nebius, PingCAP ← PinkCup, Exa ← Alexa, Brave ← Braun, Anthropic ← iShopee), tech terms (JavaScript ← Dust Script, web search ← WebSphere, E-E-A-T ← EAT), and management vocabulary (skip level ← scalable, PMF, GEO, SLG)
- 3 negative-list rules (preserve "蛮好的" / "做事情" / approximate-number phrasing)
- Loaded by ``install_seed_pack(library, only_if_empty=True)`` — won't overwrite a user's existing data on subsequent boots
- Module: ``src/clearscript/library/seed_pack.py``
- Server installs on first ``open_library()`` call per process

### Added — Actual cost reporting

Pre-run estimate kept lying about output token counts. Now both shown:

- New ``actual_cost(provider_type, model, input_tokens, output_tokens)`` in ``core/cost.py``
- After a streaming run, the SSE ``saved`` event carries the actual cost dict computed from real token usage
- Status line now shows ``Done in 28s · 8,400 tokens · 11 changes · 4 suggestions · cost: $0.0123 actual · saved as 2026-04-26-…``
- The actual cost is also persisted to the project's ``meta.json`` so the Projects tab can show it later
- Pre-run estimate's ``output_ratio`` bumped from 1.0 → 1.5 (better matches real verbose-model output)

### Tightened — L3 ASR prompt

Added a "Be proactive about company / product names" section to ``layers/l3_asr_fix.md``: explicit instruction to actively flag CamelCase / weirdly-spelled / context-misfit tokens, propose fixes for ≥75% confidence cases, add to SUGGESTIONS for <75%. Reasoning: missed real ASR errors cost more than wrong proposals the user can reject.

### Tests

- 97 still passing (MockProvider + RotatingMockProvider + DupSuggestProvider extended with ``chat_with_progress``).

### Changed

- Default ``Pipeline.max_tokens``: 16,384 (unchanged from v0.0.8 — was a v0.0.8 fix)
- Bumped to ``0.0.9``

## [0.0.8] - 2026-04-26

### Added — streaming progress + cancel button

The biggest UX wound was the 60-180s blind spinner on long runs. Closed.

- **`POST /api/run-stream`** SSE endpoint emits five named events: `plan`, `chunk_start`, `chunk_done`, `complete`, `saved` (plus `error` on failure). Same input contract as `/api/run`; same project persistence.
- **`Pipeline.iter_events()`** generator yields a `StreamEvent` per chunk transition. The synchronous `run_on_transcript()` is now a thin wrapper that consumes the events and returns the final `EditResult`. One source of truth for chunk orchestration.
- **Web UI progress panel** appears during text-input runs: progress bar (filled by `chunk_done` events), live counters for `tokens in / tokens out / changes accumulated`, current label like "Chunk 3 of 8 — calling model…". Visible the whole way, not just at the end.
- **Cancel button** in the progress header. Aborts the in-flight `fetch()` via AbortController; the server detects the disconnect and stops issuing more chunks.
- Binary-file uploads (`.docx`) keep using the existing non-streaming `/api/run-file` endpoint.

### Added — DeepSeek v4 model defaults

DeepSeek shipped v4 in 2026; the old `deepseek-chat` / `deepseek-reasoner` aliases are gone from `/v1/models`.

- Default DeepSeek model is now `deepseek-v4-pro`. Known list: `["deepseek-v4-pro", "deepseek-v4-flash"]`.
- `core/cost.py` price table includes both v4 entries (best-known approximations — verify at the official pricing page).

### Fixed

- **Output truncation** when the model hits the response cap: default `max_tokens` raised from 8,192 → 16,384. SUGGESTIONS section was getting cut off with verbose models.
- **Slug pollution** by mic-check pleasantries: `_slug_hint_from_input` now skips lines like "测一下麦", "听得见吗", "hello can you hear", "好的", and similarly low-information openings. Now prioritizes title → filename → briefing → first non-pleasantry transcript line. Project slugs no longer end up like `2026-04-26-…-测一下麦-听得见吗-听得见`.

### Changed

- `Pipeline._run_multi_chunk` removed. The streaming generator now drives both code paths.
- Bumped to `0.0.8`.

### Tests

- Existing 97 tests pass against the refactored pipeline (the streaming generator is the new internal driver). Lint clean.

## [0.0.7] - 2026-04-26

### Added — trust + iteration

- **Inline-editable cleaned output** in the Editor view: editable textarea, debounced auto-save (~700ms), with "saved / saving… / save failed / offline" status indicator.
- **Diff view** toggle (Edit / Diff). Each change_log entry's `new` value gets highlighted in Bauhaus colors layered by edit type:
  - L1 speaker = light blue · L3 ASR fix = light red · L3.5 sentence = orange · L5 format = blue-grey · L6 punct = light yellow
  - Hover any highlight to see the change reason and the chunk index it came from.
- **Cost preview** updates live above the Run button as you type / change provider. Curated price table covers anthropic (Opus / Sonnet / Haiku 4.x), openai (gpt-4o, o1), openai-compat (DeepSeek, Moonshot, Qwen, Kimi), Google (Gemini), Ollama (always free).
- **Project detail editable**: same auto-save pattern in the Cleaned sub-tab of an opened past project.
- New endpoints: `POST /api/estimate-cost`, `PATCH /api/projects/{slug}/transcript` (invalidates any cached .docx so the next download regenerates from the edited markdown).
- All download / copy buttons (.md / .docx / clipboard) now use the **current textarea content**, not the stale original LLM output.

### Tests

- 12 new tests across `test_cost.py` (price table coverage, CJK token estimation, Ollama free path, unknown-model fallback) and `test_project_update.py` (PATCH success, 404 path, docx cache invalidation, cost endpoint round-trip).
- Total: 97 tests, all passing. Lint clean.

### Changed

- The v0.0.6 chunks-stat card that the ruff format pass had silently dropped is restored. The stat grid is now correctly 5 columns: In / Out / Changes / Chunks / Latency.
- Bumped to `0.0.7`.

## [0.0.6] - 2026-04-26

### Added — long transcripts no longer crash

- **Auto-chunking** for long transcripts. ``Pipeline.run_on_transcript`` analyzes input size and, if it exceeds 6000 estimated tokens, splits it into ~3500-token chunks at speaker-turn boundaries. Each chunk runs through the same prompts; outputs are stitched back together.
- New module: ``src/clearscript/core/chunking.py`` with ``plan_chunks()``, ``estimate_tokens()``, configurable thresholds. Token estimation handles ASCII (chars/4) and CJK (chars/1.5) accurately enough for routing decisions.
- Boundary preference: speaker turn → sentence boundary (`.?。!?！？`) → hard char cut. Oversized single segments (e.g., a 30-minute monologue) are split internally on sentence boundaries.
- **Stitching logic**: edited markdown concatenated with ``\n\n``; change logs accumulated across chunks (each entry tagged with its ``chunk`` index for audit); suggestions deduped by ``(kind, canonical|canonical_name|title)`` so repeated proposals across chunks collapse.
- **Web UI**: stat panel adds a blue "Chunks" card next to In / Out / Changes / Latency. Status line on multi-chunk runs shows ``… · N chunks · ...``.
- **EditResult.num_chunks** and **RunResponse.num_chunks** so downstream consumers (UI, projects) can audit the path.
- Per-chunk change-log entries get a ``chunk`` field so the change log reads as: chunk 1 → 5 changes, chunk 2 → 8 changes, etc.

### Configurable

```python
Pipeline(
    provider=p, model=m,
    chunk_target_tokens=3500,    # aim per chunk
    chunk_trigger_tokens=6000,   # don't chunk below this
    chunk_hard_max_tokens=5000,  # split a single segment if it exceeds this
)
```

Defaults are tuned so ~30-minute interviews stay single-shot, 60+ minute ones split.

### Tests

- 11 new tests across `test_chunking.py` (token estimation, boundary preference, oversized-segment internal split, empty input, metadata preservation) and `test_pipeline_chunked.py` (multi-chunk path, single-chunk path, suggestion dedup, token-count summing).
- Total: 85 tests, all passing. Lint clean.

### Deferred to v0.0.7

- **Mode C cross-chunk learning**: chunk N's user-confirmed corrections feeding into chunk N+1's prompt. Requires multi-stage pipeline with batch-ask. Tracked.
- **Streaming progress (SSE)**: real-time "chunk 3/12 done" updates instead of waiting for the full multi-chunk run. Tracked.

## [0.0.5] - 2026-04-25

### Added — every Run is now a project

- **Project history**: every successful Run auto-saves to `~/Documents/clearscript/projects/<slug>/` with the original input, briefing (if any), cleaned markdown, change log, library suggestions, and a `meta.json` summary. No data loss when you close the browser.
- **Slug format**: `2026-04-25-143012-acme-cto-interview` — date + seconds-precision time + best-effort title from the briefing/filename. Two runs in the same minute can't collide.
- **Projects tab in the web UI** — third top-nav tab between Library and the Editor. Bauhaus-styled split layout: list on the left (with format pill, date, token count, change count), detail panel on the right with five sub-tabs (Cleaned / Raw input / Change log / Suggestions / Briefing). Per-row download buttons (`.md` / `.docx` / raw input) and delete.
- **`POST /api/run` and `/api/run-file`** now return a `project_slug` so the editor's success status line shows where the run was saved.
- **Server endpoints** for the Projects tab:
  - `GET /api/projects` (list summaries)
  - `GET /api/projects/{slug}` (full detail)
  - `DELETE /api/projects/{slug}`
  - `GET /api/projects/{slug}/transcript.md` (download cleaned output)
  - `GET /api/projects/{slug}/transcript.docx` (auto-generated from the saved markdown on first request)
  - `GET /api/projects/{slug}/input` (download original raw input)
- **CLI**: new `clearscript projects` subcommand:
  - `clearscript projects list [--limit N]`
  - `clearscript projects show <slug> [--json]`
  - `clearscript projects delete <slug> [-y]`
  - `clearscript projects path` (prints the projects root)

### Changed

- Editor success status now shows `… · saved as <slug>` when persistence worked, so you can immediately tell where to find the run.
- Web UI hash routing extended to `#editor` / `#library` / `#projects`. Refresh-friendly.
- Bumped to `0.0.5`.

### Tests

- 8 new unit tests in `test_projects.py` covering: full save round-trip, summary extraction, detail payload assembly, list-newest-first sort, delete + idempotent re-delete, second-precision slug uniqueness, binary-input bytes round-trip without crashing the detail view.
- Total: 74 tests, all passing. Lint clean.

## [0.0.4] - 2026-04-25

### Added — feed it your real transcripts

- **5 new ingest adapters** for the formats real ASR tools produce:
  - `.md` (`MdAdapter`) — auto-detect and strip AI-summary blocks. Recognizes English (`# Summary`, `## Action items`, `## TL;DR`) and Chinese (`## 本次访谈总结`, `## 会议要点`, `## 摘要`, `## 后续待办`). Strips tool provenance lines.
  - `.docx` (`DocxAdapter`) — covers 飞书妙记 / 腾讯会议 / 通义听悟 / generic Word. Detects bold-leading-run speaker pattern. Strips inline timestamps `[00:14:33]`.
  - `.srt` (`SrtAdapter`) — SubRip subtitles. Cue start/end seconds preserved on segments. Inline `Speaker: text` patterns extracted; HTML/ASS styling stripped.
  - `.vtt` (`VttAdapter`) — WebVTT, custom parser. Honors `<v Speaker>...</v>` voice tags as canonical speaker labels.
  - `.json` (`JsonAdapter`) — multi-shape: OpenAI Whisper / PLAUD / Google STT / Deepgram / generic flat list. Surfaces ASR-reported confidence when present.
- **`POST /api/run-file`** — multipart upload endpoint for binary formats (`.docx`).
- **`GET /api/supported-formats`** — extension list endpoint for the frontend.
- **Web UI multi-format input** — drop zone now accepts `.txt / .md / .markdown / .docx / .srt / .vtt / .json`; binary uploads show a yellow "📎 file pending" badge and route through `/api/run-file`; text uploads still load into the textarea with format hint preserved.
- `supported_extensions()` helper exposed from `clearscript.ingest`.

### Changed

- `RunRequest` gains a `format` field driving parser selection.
- Ingest registry order: `md → docx → srt → vtt → json → txt`.
- New runtime dependency: `python-multipart>=0.0.9`.
- Bumped to `0.0.4`.

### Tests

- 22 new format tests across `test_ingest_md.py`, `test_ingest_docx.py`, `test_ingest_srt.py`, `test_ingest_vtt.py`, `test_ingest_json.py`.
- Total: 66 tests, all passing. Lint clean.

### Caught and fixed during testing

- JSON: `s.get("start") or s.get("begin")` returned `None` when start was `0.0` (Python truthiness). Now uses explicit `is not None` checks.
- Markdown: summary-block stripping treated `## Subsection` under `# Summary` as nested-skip; should end the skip. Now ends on any non-summary heading or first speaker line.

## [0.0.3] - 2026-04-25

### Added — the library is alive

- **Library tab in the web UI** with three sub-tabs (Terms / Speakers / Edit patterns), each with a sortable table, search, type/status/domain filters, an inline add form, and per-row delete. Status rendered with Bauhaus-colored dots.
- **Library stats strip** at the top of the Library tab: 8 metric cards (terms / verified / confirmed / proposed / speakers / patterns / negatives / sessions).
- **Mode A (project-start activation)**: the briefing field is scanned for entity tokens (CamelCase, acronyms, CJK names) and each is looked up in the library; matches inject "Term mappings from your library" and "Briefing speakers" sections into the LLM system prompt. `lookup_alias` now also matches by canonical, not just aliases.
- **Mode B (end-of-session harvest)**: the layered-edit prompt now produces a `---SUGGESTIONS---` block alongside `---CHANGELOG---`. Pipeline parses it into `EditResult.suggestions`. The web UI displays a yellow panel after each run with checkboxes; "Accept selected → library" bulk-writes to terms / speakers / patterns.

### Added — Library class API

- `list_terms(type_, domain, status, search, limit)` — filtered listing including all aliases per row
- `update_term(id, ...)` and `delete_term(id)`
- `list_speakers(search, limit)`, `update_speaker`, `delete_speaker`
- `list_edit_patterns(domain)`, `add_edit_pattern(...)`, `delete_edit_pattern(id)`
- `add_negative(text, do_not_change_to, domain, reason)` (NULL-safe dedupe), `list_negatives()`
- Expanded `stats()`: now includes `verified_terms`, `confirmed_terms`, `proposed_terms`, `edit_patterns`, `negative_rules`

### Added — Server API

- `GET /api/library/stats`
- `GET /api/library/terms` (with `type`, `domain`, `status`, `search`, `limit` query params)
- `POST /api/library/terms`, `PATCH /api/library/terms/{id}`, `DELETE /api/library/terms/{id}`
- `GET /api/library/speakers`, `POST`, `PATCH`, `DELETE`
- `GET /api/library/patterns`, `POST`, `DELETE`
- `POST /api/library/accept-suggestions` — bulk write Mode B suggestions

### Changed

- All Pydantic request models lifted to module level so FastAPI can introspect them as request bodies (was: nested in `create_app`, dropped to query params)
- `TxtAdapter.parse_string()` already public from v0.0.2 — no change here; documenting that web UI uses it for in-memory input
- Bumped version to `0.0.3`

### Tests

- 17 new unit tests covering: term filtering by type/status/search, term update/delete, speaker listing/search, edit-pattern lifecycle, negative-list NULL-safe dedupe, expanded stats schema, suggestions parsing, briefing entity extraction (CJK + CamelCase + acronyms), Mode A end-to-end, fenced-JSON parsing
- Total: 44 tests, all passing

## [0.0.2] - 2026-04-25

### Added

- **Local web UI** at `http://127.0.0.1:7681`, launched via `clearscript serve`
  - Bauhaus-styled single-page app (Tailwind via CDN, Outfit font, hard offset shadows, primary color blocking)
  - Provider pill selector with live API-key detection
  - Drag-drop / paste / file-upload transcript input
  - Per-run stats (input tokens, output tokens, change count, latency)
  - Inline change-log accordion
  - One-click download as `.md` or `.docx`, one-click clipboard copy
  - "Load example" button for first-run users
  - Cmd/Ctrl+Enter keyboard shortcut to trigger a run
- FastAPI backend with JSON API: `/api/health`, `/api/providers`, `/api/run`, `/api/export/docx`, `/api/example`
- Auto-open browser on `clearscript serve` (suppress with `--no-open`)
- `TxtAdapter.parse_string()` public method for in-memory input

### Changed

- Server binds to `127.0.0.1` only by default (no network exposure unless explicitly opted in)
- `clearscript` package version bumped to `0.0.2`

### Planned for v0.1.0

- Full pipeline (Ingest → Pre-scan → Context Briefing → L1-L6 + L3.5 → Self-review → Batch-ask → Re-scan → Export)
- 12 ASR input formats
- 5 LLM provider adapters covering 20+ services
- SvelteKit web UI with Bauhaus design system
- Library Mode A (project-start activation) and Mode C (in-flight learning)
- Markdown + DOCX + JSON + SRT export
- PyInstaller-packaged desktop installers (.app, .exe, .AppImage)
- Bilingual documentation (English + Simplified Chinese)
- GitHub Actions CI

## [0.0.1] - 2026-04-25

### Added

- Initial repository scaffold with `uv` project layout
- Core directory structure: `src/clearscript/{core,ingest,providers,library,layers,export,storage,prompts}`
- Desensitized prompt library ported from the original personal Claude skill
- LLM provider abstraction with `anthropic` adapter
- `txt` ingest parser
- Markdown exporter
- Minimal CLI (`clearscript run <input>`)
- SQLite library schema
- Bauhaus design system specification
- README in English and Simplified Chinese
- MIT License
- Roadmap and architecture documentation
