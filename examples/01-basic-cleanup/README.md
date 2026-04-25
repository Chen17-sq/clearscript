# Example 01: Basic cleanup

A short synthetic ASR transcript showing the kinds of errors clearscript handles. Every name and company in this file is fictional or chosen as a stand-in for "the kind of thing that gets misheard."

## What's wrong with `input.txt`

| Issue | Where to find it | Layer that fixes it |
|---|---|---|
| Mic-check pleasantries at the start | First 2-3 turns | L2 |
| AI-generated summary at the bottom | After `---` | L2 |
| Bracketed speaker labels | `[Speaker 1]` | L1 |
| Same person multiple ASR variants | DeFi vs Difan vs 底牌 (all → Dify) | L3 |
| Company name garble | Minus → Manus | L3 |
| Product name garble | Tabby → Tavily | L3 |
| Search competitor confusion | Alexa / X → Exa | L3 |
| Big-name client garble | iShopee → Anthropic | L3 (high-stakes, would normally be flagged) |
| Tech term garble | Dust Script → JavaScript | L3 |
| Project / spec name | OpenCloud → OpenClaw | L3 |
| Memory product code | MAM-9 → Mem9 | L3 |
| Management term garble | scalable → skip level | L3 |
| Stutter | "我们当时我们当时" → "我们当时" | L3.5 |
| Missing word | "接在10%" → "在 10%" | L3 |
| Closing farewells | Last 2 turns | L2 |

## What `expected_output.md` shows

The cleaned transcript with all of the above fixed, formatted with `-` bullets and full-width Chinese colons. The actual output you get may differ slightly depending on the model — that's expected. What should be consistent: structural cleanup, library-known corrections, and no fabrication.

## Try it

```bash
uv run clearscript run examples/01-basic-cleanup/input.txt --provider claude
```

## Notes for contributors

This example is intentionally short so it runs cheaply during CI. For richer examples covering chunked / long-form / multilingual scenarios, see (forthcoming):

- `examples/02-podcast-cleanup/` — podcast transcript with two recurring guests
- `examples/03-medical-interview/` — clinical conversation with specialty terminology
- `examples/04-multilingual-meeting/` — meeting with three speakers and code-switching
