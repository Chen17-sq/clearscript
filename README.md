# clearscript

> Local-first ASR transcript editor with a compounding terminology library. Bring your own model.

[简体中文](./README.zh-CN.md) · [Roadmap](./docs/ROADMAP.md) · [Architecture](./docs/architecture.md) · [Design System](./docs/DESIGN_SYSTEM.md)

**clearscript** turns raw speech-to-text output (Feishu Miaoji, Typeless, PLAUD, Tencent Meeting, Tongyi Tingwu, Yuanbao, generic `.txt`/`.srt`/`.vtt`/`.json` and more) into archive-grade, shareable transcripts. It is **local-first** — your transcripts and terminology library never leave your machine — and **model-agnostic**: plug in Claude, GPT, Gemini, DeepSeek, Qwen, Ollama, llama.cpp, or any custom OpenAI-compatible endpoint (including Google Colab tunnels).

The project is the open-source successor to a personal Claude skill that has been used on hundreds of VC reference checks, founder interviews, board meetings, and podcast recordings.

---

## Why clearscript

Existing transcript cleanup tools fall into two camps:

- **Cloud SaaS** (Otter, Rev, Sonix): your audio and text get uploaded, processed by a closed model, and stored on someone else's servers. Privacy is a checkbox, not an architecture.
- **Generic LLM chats** (just paste into ChatGPT): every session starts from zero. The model has no memory of who your speakers are, what your industry's jargon looks like, or which corrections you've already made a hundred times.

clearscript is the third option:

| | Cloud SaaS | Plain LLM chat | clearscript |
|---|---|---|---|
| Data stays local | ✗ | ✗ | ✓ |
| Bring your own model | ✗ | ✗ | ✓ |
| Works offline (with local model) | ✗ | ✗ | ✓ |
| Compounding terminology library | ✗ | ✗ | ✓ |
| Reproducible / audit trail | ✗ | ✗ | ✓ |
| Multi-format input/output | partial | ✗ | ✓ |

---

## Status

**v0.0.1 — pre-alpha.** The repository scaffolds the architecture and ships a minimal end-to-end happy path (`txt` in → Claude → `md` out). See [ROADMAP.md](./docs/ROADMAP.md) for the full plan toward v0.1.

---

## Core ideas

### 1. Local-first

- All transcripts, projects, and the knowledge library live on your disk
- No mandatory account, no telemetry, no cloud dependency
- The only network call is the one you authorize: your chosen LLM provider
- Project format is open (Markdown + SQLite + JSON), so you own your data forever

### 2. Bring your own model

A single `providers.toml` config lets you mix and match:

```toml
default_provider = "claude"

[providers.claude]
type = "anthropic"
api_key_env = "ANTHROPIC_API_KEY"

[providers.deepseek]
type = "openai-compat"
base_url = "https://api.deepseek.com/v1"
api_key_env = "DEEPSEEK_API_KEY"

[providers.local]
type = "ollama"
base_url = "http://localhost:11434"

[providers.colab]
type = "openai-compat"
base_url = "https://abc-123.ngrok.io/v1"
```

Use a different model for different stages (cheap one for chunk pre-processing, the smart one for the heavy edit pass).

### 3. Compounding terminology library

Every session feeds a local SQLite knowledge base of terms, speakers, organizations, edit patterns, and negative rules. The next session pre-loads relevant subsets based on context, so the system gets sharper the more you use it. Markdown views auto-export so the library is human-readable and git-trackable.

### 4. Layered, auditable editing

Editing happens in named layers (speaker normalization → trimming → ASR error fix → sentence reconstruction → information preservation → dialogue formatting → punctuation). Each change is logged with `{old, new, reason, source, confidence}` so you can review, roll back, or stop the model from drifting.

---

## Quick start

> Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Chensiqi17/clearscript.git
cd clearscript
uv sync
export ANTHROPIC_API_KEY=sk-ant-...
uv run clearscript run examples/01-basic-cleanup/input.txt --provider claude
```

The cleaned transcript is written next to the input as `input.cleaned.md`.

---

## Supported inputs (target for v0.1)

| Format | Notes |
|---|---|
| `.txt` | Generic, with speaker-label heuristics |
| `.md` | With AI-summary detection |
| `.docx` | Generic + Feishu Miaoji specific layout |
| `.srt` / `.vtt` | Subtitle formats with timestamps |
| `.json` | PLAUD, common ASR APIs |
| `.html` | Feishu Miaoji web export |
| `.lrc` | Lyric-style with timestamps |
| Tongyi Tingwu | Alibaba's transcription tool export |
| Tencent Meeting | Meeting transcript export |
| Yuanbao | Tencent's AI assistant export |
| Typeless | With AI-summary stripping |

---

## Supported model providers (target for v0.1)

Five adapters cover 20+ services:

- **`anthropic`** — Claude family
- **`openai`** — GPT family
- **`openai-compat`** — DeepSeek, Moonshot/Kimi, Qwen API, Together, Groq, Fireworks, Mistral, OpenRouter, Perplexity, Zhipu, Baichuan, MiniMax, StepFun, 01.AI, Cohere, Cerebras, SambaNova, Volcano Ark, Aliyun Bailian, SiliconFlow, custom endpoints
- **`google`** — Gemini family
- **`ollama`** — local models, also covers llama.cpp server / LM Studio via OpenAI-compat mode

---

## Project structure

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
│   └── prompts/             # LLM prompt templates
├── web/                     # SvelteKit web UI (v0.1 onward)
├── tests/                   # pytest suite
├── docs/                    # MkDocs site sources
└── examples/                # Synthetic before/after samples
```

---

## Contributing

Issues and PRs welcome. See [CONTRIBUTING.md](./CONTRIBUTING.md). Particularly easy ways to help:

- **Add an ASR format adapter**: write a parser for a tool we don't yet support
- **Contribute a domain pack** (post-v0.3): industry-specific terminology bundles
- **Suggest ASR error patterns**: open an issue with `ASR original → correct` pairs you've seen in the wild

---

## License

[MIT](./LICENSE)
