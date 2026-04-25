# Quickstart

Five-minute path from "I have an ASR transcript" to "I have a cleaned deliverable."

## 1. Install

```bash
git clone https://github.com/Chensiqi17/clearscript.git
cd clearscript
uv sync
export ANTHROPIC_API_KEY=sk-ant-...   # or your provider of choice
```

## 2. Verify the providers

```bash
uv run clearscript providers
```

You should see `claude` with `✓` next to it.

## 3. Run on the bundled example

```bash
uv run clearscript run examples/01-basic-cleanup/input.txt --provider claude
```

What happens:

1. The file is parsed into a normalized transcript
2. The pipeline composes a system prompt from all 7 layer specifications
3. Claude returns the cleaned markdown plus a JSON change log
4. Three files are written next to the input:
   - `input.cleaned.md` — the cleaned transcript
   - `input.cleaned.changelog.json` — the change log
   - (optional with `--docx out.docx`) a Word document

## 4. Try with your own file

```bash
uv run clearscript run /path/to/your/transcript.txt --provider claude --docx output.docx --title "My Interview"
```

## 5. Build up your library

Every confirmed correction makes the next session sharper. To pre-populate with terms you already know:

```bash
uv run clearscript lib add-term Dify --aliases "DeFi,底牌,Difan" --type company --domain ai-infra
uv run clearscript lib add-term Mem9 --aliases "MAM-9,Mam9" --type product
uv run clearscript lib lookup DeFi
```

## 6. Use a different provider

```bash
export DEEPSEEK_API_KEY=sk-...
uv run clearscript run examples/01-basic-cleanup/input.txt --provider deepseek
```

Or keep your transcripts entirely on-device with Ollama:

```bash
uv run clearscript run examples/01-basic-cleanup/input.txt --provider ollama --model qwen2.5:14b
```

## What's next

- Read the [architecture overview](./architecture.md)
- Review the [roadmap](./ROADMAP.md) to see what's coming
- File an issue if your ASR tool isn't yet supported
