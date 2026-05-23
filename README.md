<!-- markdownlint-disable MD033 MD041 -->

<p align="center">
  <img src="./docs/assets/banner.svg" alt="clearscript — local-first ASR transcript editor with a compounding terminology library" width="100%">
</p>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/LICENSE-MIT-D02020?style=for-the-badge&labelColor=121212" alt="MIT License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/PYTHON-3.11+-1040C0?style=for-the-badge&labelColor=121212" alt="Python 3.11+"></a>
  <a href="https://github.com/Chen17-sq/clearscript/releases"><img src="https://img.shields.io/badge/VERSION-0.0.18-F0C020?style=for-the-badge&labelColor=121212" alt="v0.0.18"></a>
  <a href="https://github.com/Chen17-sq/clearscript/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Chen17-sq/clearscript/ci.yml?branch=main&style=for-the-badge&labelColor=121212&color=121212&label=CI" alt="CI"></a>
  <a href="./README.zh-CN.md"><img src="https://img.shields.io/badge/简体中文-FFFFFF?style=for-the-badge&labelColor=121212" alt="Simplified Chinese"></a>
</p>

<p align="center">
  <b>Local-first</b>  ·  <b>Bring your own model</b>  ·  <b>Compounding library</b>
</p>

<hr>

## You just spent 45 minutes fixing the same transcript errors. Again.

Your ASR tool gives you 95% of the transcript right. The other 5% is mind-numbing:

- "Speaker 2" never gets a real name
- "Dify" came back as "DeFi"
- "PingCAP" came back as "PinkCup"
- The mic-check pleasantries you delete every time
- The same misheard jargon you fixed last week

Then tomorrow you'll do another interview and start over.

**clearscript watches you fix it once. Next time, it remembers.**

> [!TIP]
> Drop in a raw transcript → pick any model → click Run → edit inline → download `.docx`.
> Your fixes go into a local terminology library. Run #10 barely needs touching.

This started as a personal Claude skill that ran on a few hundred VC reference checks, founder interviews, board meetings, and podcast cleanups. The library learned. The 45 minutes shrank. Now it's MIT-licensed, local-first, and yours to use.

<table>
<tr>
<td width="33%" valign="top">

### 🟥 &nbsp;Local-first

Transcripts and the terminology library live on your disk. No accounts, no telemetry, no cloud dependency. The only network call is the one you authorize — your chosen LLM provider.

</td>
<td width="33%" valign="top">

### 🟦 &nbsp;Bring your own model

Five adapters cover **20+ services**: Anthropic · OpenAI · DeepSeek · Moonshot · Qwen · Together · Groq · Fireworks · Mistral · OpenRouter · Google Gemini · Ollama · llama.cpp · LM Studio · custom endpoints (incl. Colab tunnels).

</td>
<td width="33%" valign="top">

### 🟨 &nbsp;Compounding library

A local SQLite knowledge base of terms, speakers, and edit patterns that grows with every session. Next session pre-loads the relevant subset automatically. Markdown views auto-export — human-readable and git-trackable.

</td>
</tr>
</table>

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

## Why it exists

Existing transcript-cleanup tools fall into two camps:

- **Cloud SaaS** (Otter, Rev, Sonix): your audio and text get uploaded, processed by a closed model, and stored on someone else's servers. Privacy is a checkbox, not an architecture.
- **Generic LLM chats** (paste into ChatGPT): every session starts from zero. The model has no memory of who your speakers are, what your industry's jargon looks like, or which corrections you've made a hundred times before.

clearscript is the third option:

<table>
<thead>
<tr>
  <th></th>
  <th align="center">Cloud SaaS</th>
  <th align="center">Plain LLM chat</th>
  <th align="center"><b>clearscript</b></th>
</tr>
</thead>
<tbody>
<tr><td>Data stays local</td><td align="center">✗</td><td align="center">✗</td><td align="center"><b>✓</b></td></tr>
<tr><td>Bring your own model</td><td align="center">✗</td><td align="center">✗</td><td align="center"><b>✓</b></td></tr>
<tr><td>Works offline (with local model)</td><td align="center">✗</td><td align="center">✗</td><td align="center"><b>✓</b></td></tr>
<tr><td>Compounding terminology library</td><td align="center">✗</td><td align="center">✗</td><td align="center"><b>✓</b></td></tr>
<tr><td>Reproducible / audit trail</td><td align="center">✗</td><td align="center">✗</td><td align="center"><b>✓</b></td></tr>
<tr><td>Multi-format input/output</td><td align="center">partial</td><td align="center">✗</td><td align="center"><b>✓</b></td></tr>
</tbody>
</table>

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

## Quick start

> Requires Python 3.11+.

**Install as a global tool** (recommended for non-developers):

```bash
# with uv (https://docs.astral.sh/uv/) — fastest
uv tool install git+https://github.com/Chen17-sq/clearscript.git

# or with pipx (https://pipx.pypa.io/)
pipx install git+https://github.com/Chen17-sq/clearscript.git

# set your key (any one is enough)
export ANTHROPIC_API_KEY=sk-ant-...
# or DEEPSEEK_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY

clearscript serve
```

**Or clone for development:**

```bash
git clone https://github.com/Chen17-sq/clearscript.git
cd clearscript
uv sync
export ANTHROPIC_API_KEY=sk-ant-...
```

### Option 1 — Web UI (recommended)

```bash
clearscript serve         # or: uv run clearscript serve
```

Opens **http://127.0.0.1:7681** in your browser. Bauhaus-styled single-page interface: pick a provider pill, paste or drag in your transcript, click **Clean transcript**, download as `.md` / `.docx`.

### Option 2 — CLI

```bash
clearscript run examples/01-basic-cleanup/input.txt --provider claude
```

The cleaned transcript is written next to the input as `input.cleaned.md`, with a JSON change log alongside.

Prefer a different model?

```bash
# OpenAI-compatible (DeepSeek, Moonshot, Qwen, Together, Groq, Fireworks, Mistral, OpenRouter, ...)
export DEEPSEEK_API_KEY=sk-...
clearscript run input.txt --provider deepseek

# 100% local (Ollama / llama.cpp server / LM Studio)
clearscript run input.txt --provider ollama --model qwen2.5:14b
```

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

## Status

> **v0.0.14 — alpha.** Local web UI with Editor + Library + Projects tabs; multi-format ingest (`.txt / .md / .docx / .srt / .vtt / .json`); compounding terminology library with **Mode A** (library-into-prompt) + **Mode B** (harvest suggestions, with a persistent inbox across all runs) + **Mode C** (cross-chunk consistency); universal seed pack of 17 common ASR mistakes ships pre-installed; every Run auto-saves as a project to `~/Documents/clearscript/projects/`; **long transcripts (60+ min) are auto-chunked** at speaker boundaries and stitched back together; **Re-run** any saved project against the current library and a side-by-side **diff modal** shows exactly what your library tweak changed; **library health dashboard** flags duplicates / low-confidence / stale terms; **library export/import** as JSON or git-friendly markdown; **pre-flight cost confirmation** so a 60-min Opus run doesn't surprise you. Token-level live streaming so you watch the cleaned text appear in real time. Full v0.1 plan: see [ROADMAP](./docs/ROADMAP.md).

### Supported input formats today

| Format | Source examples |
|---|---|
| `.txt` | Generic, with speaker-label heuristics |
| `.md` | Auto-strips AI-summary blocks (English + Chinese) |
| `.docx` | 飞书妙记 / 腾讯会议 / 通义听悟 / generic Word |
| `.srt` | SubRip subtitle, time-stamped |
| `.vtt` | WebVTT (honors `<v Speaker>` voice tags) |
| `.json` | OpenAI Whisper / PLAUD / Google STT / Deepgram / generic flat list |

<table>
<tr>
<td width="50%" valign="top">

### Shipped in v0.0.1

- 5 LLM provider adapters (20+ services)
- `.txt` ingest with speaker heuristics
- SQLite library: terms / aliases / speakers / patterns / sessions / negatives + FTS5
- Single-pass pipeline (ingest → LLM → md/docx + JSON changelog)
- CLI: `run`, `providers`, `lib stats / add-term / lookup`
- Bundled prompt library (system + 7 stage prompts + 7 layer specs)
- User overrides via `~/.config/clearscript/prompts/`
- Bilingual docs, MIT license, full GitHub templates
- 27 unit tests, CI on macOS + Linux + Windows × Py 3.11/3.12/3.13

</td>
<td width="50%" valign="top">

### Coming in v0.1

- 12 ASR input formats (Feishu Miaoji, Typeless, Tongyi Tingwu, Tencent Meeting, Yuanbao, PLAUD, SRT, VTT, JSON, HTML, LRC, etc.)
- Full pipeline decomposition (pre-scan → context briefing → chunking → self-review → batch-ask → re-scan)
- L3.5 sentence-level reasoning layer
- SvelteKit web UI with [Bauhaus design system](./docs/DESIGN_SYSTEM.md)
- Library Mode A (project-start activation) and Mode C (in-flight learning)
- PyInstaller-packaged desktop installers (.app · .exe · .AppImage)
- MkDocs Material doc site auto-deployed to GitHub Pages

</td>
</tr>
</table>

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

## Design principles (non-negotiable)

These constrain every feature decision:

- 🟥 &nbsp;**No telemetry.** Ever. Not opt-in, not anonymous, not "just for crashes."
- 🟦 &nbsp;**No mandatory network calls** beyond the user's chosen LLM provider.
- 🟨 &nbsp;**No proprietary data formats.** Markdown, SQLite, JSON — readable from outside clearscript forever.
- ⬛ &nbsp;**No assumed cloud services.** If it requires an account somewhere, it's behind a setting that's off by default.

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

## Project layout

```
clearscript/
├── src/clearscript/         # Python package
│   ├── core/                # Pipeline orchestration
│   ├── ingest/              # ASR-format parsers
│   ├── providers/           # LLM provider adapters
│   ├── library/             # Terminology knowledge base
│   ├── layers/              # Edit layers (L1-L6 + L3.5 + Self-review)
│   ├── export/              # Output formatters
│   ├── storage/             # Project filesystem layout
│   └── prompts/             # LLM prompt templates (markdown, user-overridable)
├── web/                     # SvelteKit web UI (v0.1 onward)
├── tests/                   # pytest suite
├── docs/                    # MkDocs site sources + design system + assets
└── examples/                # Synthetic before/after samples
```

Read [`docs/architecture.md`](./docs/architecture.md) for the full pipeline contract.

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

## Use it your way

| Form | For who | How to install |
|---|---|---|
| **Local app** (web UI) | Anyone who wants the full editor — Library tab, Project history, inline diff, cost preview | `git clone … && uv sync && uv run clearscript serve` |
| **Claude skill** | Anyone using Claude Code or the Claude Agent SDK | Download `clearscript.skill` from [Releases](https://github.com/Chen17-sq/clearscript/releases) → unzip into `~/.claude/skills/` |

Both share **the exact same prompt library**. Improvements to the standalone app's editing rules ship into the skill on the next release.

→ Read the [manifesto](./docs/manifesto.md) for why local-first matters here.

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

## Contributing

Issues and PRs welcome. See [`CONTRIBUTING.md`](./CONTRIBUTING.md). Easy ways to help:

- **Add an ASR format adapter** — write a parser for a tool we don't yet support
- **Suggest ASR error patterns** — open an issue with `ASR original → correct` pairs you've seen
- **Test with your own model** — try a provider we haven't smoke-tested and report
- **Contribute a domain pack** (post-v0.3) — industry-specific terminology bundles

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

<p align="center">
  <img src="./docs/assets/logo.svg" alt="clearscript logo" width="80">
</p>
<p align="center"><sub><b>clearscript</b> · Released under the <a href="./LICENSE">MIT License</a> · Built for people who care about their transcripts</sub></p>
