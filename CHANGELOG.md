# Changelog

All notable changes to clearscript will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
