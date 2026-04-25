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
- [ ] Context Briefing UI flow (CLI prompts + web UI)
- [ ] Chunking by semantic boundary (target ~3-5k tokens per chunk)
- [ ] L3.5 sentence-level reasoning layer
- [ ] Self-review stage
- [ ] Batch-ask UI
- [ ] Diff-aware Re-scan stage
- [ ] Resume / rollback (`clearscript resume`, `clearscript rollback`)
- [ ] Audit trail with full change provenance

### Ingest (12 formats)
- [x] `.txt`
- [ ] `.md` with AI-summary detection
- [ ] `.docx` (generic + Feishu Miaoji specific)
- [ ] `.srt` / `.vtt`
- [ ] `.json` (PLAUD, common ASR APIs)
- [ ] `.html` (Feishu Miaoji web export)
- [ ] `.lrc`
- [ ] Tongyi Tingwu (Alibaba)
- [ ] Tencent Meeting
- [ ] Yuanbao
- [ ] Typeless (with summary stripping)

### Library
- [ ] Mode A: project-start activation with related-entity expansion
- [ ] Mode C: in-flight learning from batch-ask confirmations
- [ ] Markdown view with two-way sync
- [ ] CLI: `lib search`, `lib export`, `lib import`
- [ ] Universal pack seeded at install

### Frontend
- [ ] FastAPI server with SSE/WebSocket progress streaming
- [ ] SvelteKit web UI (Bauhaus design system)
- [ ] Library / Editor / Settings views
- [ ] Real-time diff display
- [ ] Cost estimator before each LLM call

### Distribution
- [ ] PyInstaller-packaged single-file executable for macOS / Windows / Linux
- [ ] Homebrew formula
- [ ] Docker image

### Documentation
- [ ] MkDocs Material site auto-deployed to GitHub Pages
- [ ] Per-provider setup guides
- [ ] Per-workflow examples (VC ref, podcast cleanup, medical interview, etc.)

## v0.2.0 — Quality and trust

- [ ] Mode B: end-of-session harvest UI
- [ ] Library health dashboard (confidence decay, conflict detection, duplicate detection)
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
