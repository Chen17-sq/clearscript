# Architecture

clearscript is a layered system. This document explains how the layers fit together so contributors can find the right place for changes.

## Top-level layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Distribution                                                   │
│  pipx · Homebrew · Tauri desktop (v0.3) · Docker · GitHub .skill│
├─────────────────────────────────────────────────────────────────┤
│  Frontends                                                      │
│  CLI (typer) · Local Web UI (SvelteKit, Bauhaus design)         │
├─────────────────────────────────────────────────────────────────┤
│  HTTP/WS API                                                    │
│  FastAPI (v0.1) — same surface for CLI batch jobs and web UI    │
├─────────────────────────────────────────────────────────────────┤
│  Core engine (pure Python — `src/clearscript/`)                 │
│  ├─ Ingest         (parsers per ASR format)                     │
│  ├─ Providers      (LLM adapters)                               │
│  ├─ Pipeline       (stage orchestration)                        │
│  ├─ Layers         (L1-L6 + L3.5 + Self-review + Re-scan)       │
│  ├─ Library        (SQLite + FTS + embeddings)                  │
│  ├─ Export         (md / docx / json / srt / pdf)               │
│  ├─ Storage        (project filesystem)                         │
│  └─ Prompts        (markdown templates, user-overridable)       │
├─────────────────────────────────────────────────────────────────┤
│  Persistence                                                    │
│  SQLite (canonical store) · Markdown views (export) · Files     │
└─────────────────────────────────────────────────────────────────┘
```

## Pipeline contract (target — v0.1)

```
┌─────────────────┐
│ 0. Ingest       │ → raw/ + parsed.json
├─────────────────┤
│ 1. Pre-scan     │ → prescan.json (domain hints, speaker count, risk zones)
├─────────────────┤
│ 2. Briefing     │ → context.json (5 user-confirmed seeds)
├─────────────────┤
│ 2.5 Lib activate│ → activated.json (subset relevant to this session)
├─────────────────┤
│ 3. Chunking     │ → chunks/000.md, 001.md, ...
├─────────────────┤
│ 4. L1-L6+L3.5   │ → edited_chunks/*.md + change_log/*.json
├─────────────────┤
│ 5. Stitching    │ → stitched.md + cross-chunk consistency report
├─────────────────┤
│ 6. Self-review  │ → review_report.json (additional fixes, rollbacks, escalations)
├─────────────────┤
│ 7. Batch-ask    │ → questions.json (single user-facing batch)
├─────────────────┤
│ 8. Confirm      │ → confirmations.json (user decisions)
├─────────────────┤
│ 9. Re-scan      │ → final.md (apply confirmations document-wide)
├─────────────────┤
│ 10. Export      │ → final.docx / final.json / final.srt / ...
├─────────────────┤
│ 11. Harvest     │ → suggestions.json (new terms / speakers / patterns for library)
└─────────────────┘
```

Every stage produces a serializable artifact saved to the project working directory. The pipeline is **resumable** (``clearscript resume <project>``) and **rollback-able** (``clearscript rollback --to-stage 5``). v0.0.1 collapses the whole pipeline into a single LLM call; v0.1 unfolds the stages.

## Library lifecycle

A term in the library moves through these states:

```
proposed ──► confirmed ──► verified
   │            │              │
   ▼            ▼              ▼
disputed ◄──── (negative feedback) ────► deprecated
```

- `proposed`: created automatically; never auto-applied without context evidence
- `confirmed`: user accepted at least once; safe to apply with logging
- `verified`: confirmed ≥ 3 times; high-confidence auto-application
- `disputed`: user rejected the suggestion; lowers confidence
- `deprecated`: archived; no longer matched

Confidence decays slowly when entries go unused (target v0.2), preventing
library rot.

## Library integration modes

Three integration points in the pipeline:

- **Mode A — Project start**: at Stage 2.5, the library activates a relevant subset based on the user's briefing seeds (companies → related terms, speakers → known affiliations, domain → pack contents).
- **Mode B — End harvest**: at Stage 11, surfaced as a single review pass: "here are 19 new things this session learned, accept all / pick / dismiss."
- **Mode C — In-flight**: every batch-ask confirmation immediately writes to the library, so the same session benefits from earlier confirmations on later chunks.

## Provider abstraction

All adapters implement the same `LLMProvider` protocol (`providers/base.py`). The pipeline never imports a specific provider — it works against the protocol. Five concrete adapters cover 20+ services (see `README.md`).

Provider config lives in `~/.config/clearscript/providers.toml`. API keys are read from environment variables, the config file, or the OS keyring (added v0.2).

## Prompts as artifacts

Prompts live as markdown files in `src/clearscript/prompts/`. Two reasons:

1. **Editable by non-engineers.** The whole point of an editing tool is that the rules of editing are user-facing.
2. **User overrides.** A user can drop a file at `~/.config/clearscript/prompts/layers/l3_asr_fix.md` and override the bundled default without forking.

The `compose_edit_prompt()` function assembles the system prompt from base + stage + layer specs + user briefing + library context.

## Storage model

Two stores, one source of truth:

- **SQLite** (`<data_dir>/library/library.db`) is canonical for the terminology library
- **Markdown views** (`<data_dir>/library/markdown_view/*.md`) auto-export from SQLite for human review and git tracking

Project data lives on disk in plain folders (`~/Documents/clearscript/projects/<slug>/`):

```
<slug>/
├── meta.json
├── raw/        # original uploads (immutable)
├── parsed/     # NormalizedTranscript JSON
├── working/    # per-stage intermediates
├── final/      # exported deliverables
└── changelog.md
```

This way, the user can move, back up, encrypt, or git-track projects without the application's involvement.

## Why local-first matters here

- Transcripts are often confidential — board meetings, founder interviews, medical conversations
- Terminology libraries become the user's institutional memory; that should never be sharecropped
- Bring-your-own-model means the user picks the trust boundary, not us
- Open data formats mean the user is never locked in
