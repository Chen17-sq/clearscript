# Changelog

All notable changes to clearscript will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
