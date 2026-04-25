# Installation

## Requirements

- Python 3.11 or higher
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`
- An LLM provider API key, **or** a local model server (Ollama / llama.cpp / LM Studio)

## Install via uv (recommended for developers)

```bash
git clone https://github.com/Chensiqi17/clearscript.git
cd clearscript
uv sync
```

This creates a `.venv/` and installs everything. Run any command via `uv run`:

```bash
uv run clearscript --help
```

## Install via pipx (recommended for end users)

```bash
pipx install git+https://github.com/Chensiqi17/clearscript.git
clearscript --help
```

## Provider setup

clearscript reads provider configuration from `~/.config/clearscript/providers.toml`. The default config supports five built-in providers; just set the API key for the one you want.

### Anthropic Claude

```bash
export ANTHROPIC_API_KEY=sk-ant-...
clearscript run interview.txt --provider claude --model claude-opus-4-7
```

### OpenAI

```bash
export OPENAI_API_KEY=sk-...
clearscript run interview.txt --provider openai --model gpt-4o
```

### DeepSeek (and other OpenAI-compatible)

```bash
export DEEPSEEK_API_KEY=sk-...
clearscript run interview.txt --provider deepseek --model deepseek-chat
```

### Google Gemini

```bash
export GEMINI_API_KEY=...
clearscript run interview.txt --provider gemini
```

### Ollama (local)

Make sure Ollama is running (`ollama serve`) and you've pulled a model (`ollama pull qwen2.5:14b`):

```bash
clearscript run interview.txt --provider ollama --model qwen2.5:14b
```

### Custom provider

Edit `~/.config/clearscript/providers.toml`:

```toml
[providers.my-custom]
type = "openai-compat"
base_url = "https://my-server.example.com/v1"
api_key_env = "MY_CUSTOM_KEY"
default_model = "my-model"
```

Use it:

```bash
clearscript run interview.txt --provider my-custom
```

## Verify installation

```bash
clearscript version
clearscript providers
clearscript lib stats
```

If `providers` shows `✗` next to your provider, set the env var or add the key to the config file.
