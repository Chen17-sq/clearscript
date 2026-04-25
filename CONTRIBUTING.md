# Contributing to clearscript

First off, thanks for considering a contribution. clearscript is a small project with big ambitions — every adapter, every domain pack, every bug report makes the next user's experience better.

## Ways to contribute

### 1. Report bugs

Open an issue using the [Bug report template](.github/ISSUE_TEMPLATE/bug_report.yml). Include:

- The ASR tool that produced your input
- The model provider and model you used
- The exact CLI command or UI action
- The error message or unexpected output
- A minimal synthetic input that reproduces (no real PII please)

### 2. Suggest a new ASR format adapter

Open an issue using the [New ASR format template](.github/ISSUE_TEMPLATE/new_asr_format.yml). Include:

- The tool name and a link to it
- A small synthetic export (anonymized) showing the format
- Whether you can contribute the parser yourself

### 3. Suggest a new model provider

Open an issue using the [New provider template](.github/ISSUE_TEMPLATE/new_provider.yml). Most providers can be added via the existing `openai-compat` adapter — file an issue first so we can confirm the right path before you write code.

### 4. Contribute ASR correction patterns (post-v0.3)

Domain packs let users share curated terminology bundles. Once the pack system ships in v0.3, see `docs/pack-development.md` for instructions.

### 5. Contribute code

#### Setting up

```bash
git clone https://github.com/Chensiqi17/clearscript.git
cd clearscript
uv sync --extra dev
uv run pytest
```

#### Style

- We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting
- Run `uv run ruff check . && uv run ruff format .` before opening a PR
- Type hints encouraged; `mypy` runs in CI but doesn't block

#### Tests

- Unit tests for any new parser, layer, or exporter are required
- Integration tests use a `MockLLMProvider` (no real API calls)
- E2E tests with real models are run on `main` only

#### Pull requests

- Open against `main`
- Reference any issue your PR closes (`Closes #123`)
- Describe what changes and why
- Include before/after for user-visible changes
- Keep PRs focused — small, single-purpose changes are reviewed faster

## Local-first principles

When proposing changes, please respect the project's foundational commitments:

- **No telemetry** of any kind, including opt-in
- **No mandatory network calls** beyond the user's chosen LLM provider
- **No data formats that lock users in** — everything readable from outside clearscript
- **No assumed cloud services** — if it requires an account somewhere, it goes behind a setting that's off by default

## Code of Conduct

By participating, you agree to abide by the [Contributor Covenant Code of Conduct](./CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](./LICENSE).
