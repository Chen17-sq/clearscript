"""CLI smoke tests."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from clearscript import __version__
from clearscript.cli import app
from clearscript.providers.base import ChatResponse

runner = CliRunner()


class CliMockProvider:
    """Provider that returns a parseable three-section response.

    The CLI's edit pipeline calls ``chat_with_progress`` (via iter_events
    under the hood), so we implement that one along with chat/stream.
    """

    name = "mock"

    def __init__(self) -> None:
        self.response = (
            "Speaker A:\n- Cleaned line.\n"
            "---CHANGELOG---\n[]\n"
            "---SUGGESTIONS---\n[]"
        )

    def chat(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        return ChatResponse(
            text=self.response,
            input_tokens=10,
            output_tokens=5,
            model=model,
            provider=self.name,
            latency_ms=1.0,
        )

    def stream(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        yield self.response

    def chat_with_progress(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        yield ("delta", self.response)
        yield ("done", self.chat(messages, model, **kwargs))


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """Patch config dirs + provider builder so CLI commands work offline."""
    cfg_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    cfg_dir.mkdir()
    data_dir.mkdir()
    monkeypatch.setattr("clearscript.config.CONFIG_DIR", cfg_dir)
    monkeypatch.setattr("clearscript.config.DATA_DIR", data_dir)
    monkeypatch.setattr("clearscript.config.CONFIG_FILE", cfg_dir / "config.toml")
    monkeypatch.setattr(
        "clearscript.config.PROVIDERS_FILE", cfg_dir / "providers.toml"
    )
    monkeypatch.setattr("clearscript.cli.build_provider", lambda _c: CliMockProvider())
    return tmp_path


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_providers_lists_default_providers() -> None:
    result = runner.invoke(app, ["providers"])
    assert result.exit_code == 0
    assert "claude" in result.stdout
    assert "ollama" in result.stdout


def test_run_command_writes_cleaned_md(cli_env, tmp_path) -> None:
    """`clearscript run input.txt` should produce input.cleaned.md + changelog."""
    input_path = tmp_path / "sample.txt"
    input_path.write_text("Speaker 1: hello.\nSpeaker 2: hi.\n", encoding="utf-8")
    result = runner.invoke(
        app,
        ["run", str(input_path), "--provider", "claude", "--no-library"],
    )
    assert result.exit_code == 0, result.stdout
    cleaned = input_path.with_suffix(".cleaned.md")
    assert cleaned.is_file()
    assert "Cleaned line" in cleaned.read_text(encoding="utf-8")
    # Companion changelog file lands next to it.
    log_path = cleaned.with_suffix(".changelog.json")
    assert log_path.is_file()


def test_projects_list_command(cli_env, tmp_path) -> None:
    # Generate a project via run.
    input_path = tmp_path / "x.txt"
    input_path.write_text("Speaker 1: hi.\n", encoding="utf-8")
    runner.invoke(app, ["run", str(input_path), "--provider", "claude", "--no-library"])

    result = runner.invoke(app, ["projects", "list"])
    assert result.exit_code == 0
    # The Rich table prints column headers and at least one row.
    assert "Slug" in result.stdout or "slug" in result.stdout.lower()


def test_projects_rerun_creates_sibling(cli_env, tmp_path) -> None:
    """`clearscript projects rerun <slug>` produces a -rerun sibling project."""
    input_path = tmp_path / "x.txt"
    input_path.write_text("Speaker 1: hi there.\n", encoding="utf-8")
    runner.invoke(app, ["run", str(input_path), "--provider", "claude", "--no-library"])

    # Look up the project slug just created.
    from clearscript.config import load_config
    from clearscript.storage import ProjectStore

    summaries = ProjectStore(load_config().projects_root).list_summaries()
    assert summaries, "expected at least one saved project"
    orig_slug = summaries[0]["slug"]

    result = runner.invoke(
        app, ["projects", "rerun", orig_slug, "--provider", "claude"]
    )
    assert result.exit_code == 0, result.stdout
    assert "new project" in result.stdout.lower()

    # Confirm sibling slug exists.
    new_summaries = ProjectStore(load_config().projects_root).list_summaries()
    slugs = [s["slug"] for s in new_summaries]
    assert any(s.endswith("-rerun") for s in slugs)
    assert orig_slug in slugs  # original preserved


def test_projects_rerun_missing_slug_exits_with_error(cli_env) -> None:
    result = runner.invoke(app, ["projects", "rerun", "no-such-slug"])
    assert result.exit_code == 1
    # Error printed via stderr is captured by runner — check stdout for friendly msg.


def test_lib_lookup_command(cli_env) -> None:
    """`clearscript lib lookup <alias>` finds seeded terms."""
    # Force-install seed pack first by opening server which auto-seeds.
    from clearscript.config import load_config
    from clearscript.library import Library, install_seed_pack

    cfg = load_config()
    lib = Library(cfg.library_path)
    install_seed_pack(lib)
    lib.close()

    result = runner.invoke(app, ["lib", "lookup", "DeFi"])
    assert result.exit_code == 0
    assert "Dify" in result.stdout
