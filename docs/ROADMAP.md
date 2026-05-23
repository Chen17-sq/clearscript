# Roadmap

## v0.0.1 — Minimum scaffold (current)

- [x] Repository structure with uv-managed Python package
- [x] LLM provider abstraction with five adapters (Anthropic, OpenAI, OpenAI-compat, Google, Ollama) covering 20+ services
- [x] Plain `.txt` ingest adapter with speaker-label heuristics
- [x] Single-pass pipeline (ingest → compose prompts → LLM → markdown out)
- [x] SQLite library with terms / aliases / speakers / sessions
- [x] Markdown and DOCX exporters
- [x] CLI (`clearscript run`, `clearscript providers`, `clearscript lib`)
- [x] Bundled desensitized prompt library (system + 7 layers + 5 stage prompts)
- [x] Bilingual README, MIT license, GitHub issue/PR templates
- [x] CI (lint + tests on macOS / Linux / Windows × Py 3.11/3.12/3.13)

## v0.1.0 — Full pipeline (target: end of v0.0.1 + 8 weeks)

### Pipeline
- [ ] Stage decomposition (each stage produces serializable artifact)
- [ ] Pre-scan stage with structured JSON output
- [x] Context Briefing UI flow (web UI ships in v0.0.2)
- [x] Chunking by semantic boundary at speaker turns (v0.0.5, ~3.5k target tokens)
- [x] L3.5 sentence-level reasoning layer (in prompts/layers/)
- [ ] Self-review stage
- [ ] Batch-ask UI
- [ ] Diff-aware Re-scan stage
- [x] Project re-run (`clearscript projects rerun <slug>` + UI button, v0.0.11)
- [x] Project compare (`/api/projects/{slug}/compare?with=...` + UI modal, v0.0.13)
- [x] Audit trail with full change provenance (change_log.json per project)

### Ingest (12 formats)
- [x] `.txt`
- [x] `.md` with AI-summary detection (v0.0.4)
- [x] `.docx` (generic + Feishu Miaoji specific) (v0.0.4)
- [x] `.srt` / `.vtt` (v0.0.4)
- [x] `.json` (PLAUD, common ASR APIs) (v0.0.4)
- [ ] `.html` (Feishu Miaoji web export)
- [ ] `.lrc`
- [ ] Tongyi Tingwu (Alibaba)
- [ ] Tencent Meeting
- [ ] Yuanbao
- [ ] Typeless (with summary stripping)

### Library
- [x] Mode A: library-into-prompt activation (v0.0.3, fixed to scan transcript itself v0.0.11)
- [x] Mode B: end-of-session harvest UI (v0.0.3 per-run, v0.0.14 persistent inbox)
- [x] Mode C: cross-chunk learning (v0.0.11)
- [x] Markdown view (`lib export --md`, v0.0.13)
- [x] CLI: `lib search` (v0.0.13), `lib export` (v0.0.12), `lib import` (v0.0.12)
- [x] Universal pack seeded at install (17 terms, 3 negatives, v0.0.9)
- [x] Health check (duplicates / low-conf / stale, v0.0.13)
- [x] Negatives CRUD (v0.0.13)
- [x] Bulk delete (v0.0.12)

### Frontend
- [x] FastAPI server with SSE progress streaming (v0.0.8 + v0.0.9 token-level deltas)
- [x] Single-page web UI in Bauhaus design system (v0.0.2)
- [x] Library / Editor / Projects views (v0.0.3)
- [x] Real-time diff display (rerun compare modal, v0.0.13)
- [x] Cost estimator before each LLM call (v0.0.9 + pre-flight confirmation v0.0.14)

### Distribution
- [x] `uv tool install` + `pipx install` from git (v0.0.11)
- [ ] PyInstaller-packaged single-file executable for macOS / Windows / Linux
- [ ] Homebrew formula
- [ ] Docker image

### Documentation
- [x] MkDocs Material site auto-deployed to GitHub Pages (live at chen17-sq.github.io/clearscript)
- [ ] Per-provider setup guides
- [ ] Per-workflow examples (VC ref, podcast cleanup, medical interview, etc.)

## v0.2.0 — Quality and trust

- [x] Mode B: end-of-session harvest UI (v0.0.3 + persistent inbox v0.0.14)
- [x] Library health dashboard (duplicates / low-conf / stale, v0.0.13 + UI v0.0.14)
- [ ] Privacy redact mode (local NER → mask before LLM → unmask after)
- [ ] Postgres adapter as alternative to SQLite (for team / shared library)
- [ ] OS keyring for API key storage
- [ ] Local embedding model (BGE-small) for semantic library search
- [ ] PDF / JSON / SRT export
- [ ] Encrypted project export (`*.zip.enc`)

## v0.3.0 — Ecosystem

- [ ] Domain pack system + 5 official packs (vc / ai-infra / consumer / medical / podcast)
- [ ] Plugin system for custom layers and ingest adapters
- [ ] Tauri desktop app (auto-update, system tray, file associations, native menus)
- [ ] Multi-language UI (en + zh-CN, with framework for more)
- [ ] Library bulk operations (merge / split / retag / mass-deprecate)

## v0.4+ — Polish and scale

- [ ] Full-text search across all transcripts (FTS5)
- [ ] Speaker fingerprinting across sessions
- [ ] Project templates (one-click setup for common workflows)
- [ ] Notion / Obsidian integration
- [ ] Optional git-based collaboration / sync
- [ ] Read-only mobile companion (PWA)

## Design principles that constrain the roadmap

These are not negotiable:

- No telemetry, ever
- No mandatory network calls beyond user-configured LLM provider
- No proprietary data formats
- No assumed cloud services
- No data collection or aggregation across users

Features that conflict with the above will not ship, regardless of utility.
