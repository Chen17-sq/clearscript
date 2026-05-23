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


def test_lib_search_command(cli_env) -> None:
    """`clearscript lib search` returns a Rich table of matching canonicals."""
    from clearscript.config import load_config
    from clearscript.library import Library

    cfg = load_config()
    lib = Library(cfg.library_path)
    lib.add_term(canonical="Anthropic", aliases=["iShopee"])
    lib.add_term(canonical="OpenAI", aliases=["O AI"])
    lib.close()

    result = runner.invoke(app, ["lib", "search", "Anthropic"])
    assert result.exit_code == 0
    assert "Anthropic" in result.stdout


def test_lib_search_empty_result(cli_env) -> None:
    result = runner.invoke(app, ["lib", "search", "DefinitelyNotInLibrary"])
    assert result.exit_code == 0
    assert "No matches" in result.stdout


def test_lib_export_writes_json(cli_env, tmp_path) -> None:
    """`clearscript lib export <path>` writes a valid versioned export."""
    import json

    from clearscript.config import load_config
    from clearscript.library import Library

    cfg = load_config()
    lib = Library(cfg.library_path)
    lib.add_term(canonical="ExportMe", aliases=["em"])
    lib.close()

    export_path = tmp_path / "exported.json"
    result = runner.invoke(app, ["lib", "export", str(export_path)])
    assert result.exit_code == 0, result.stdout
    assert export_path.is_file()

    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["format"] == "clearscript-library-export"
    canonicals = {t["canonical"] for t in payload["terms"]}
    assert "ExportMe" in canonicals


def test_lib_import_round_trip(cli_env, tmp_path) -> None:
    """Export then import — terms survive the round trip via CLI."""
    import json

    payload = {
        "format": "clearscript-library-export",
        "schema_version": 1,
        "terms": [
            {"canonical": "ImportedTerm", "aliases": ["it"], "type": "company"}
        ],
        "speakers": [],
        "edit_patterns": [],
        "negatives": [],
    }
    import_path = tmp_path / "to-import.json"
    import_path.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(app, ["lib", "import", str(import_path)])
    assert result.exit_code == 0, result.stdout
    assert "terms_added: 1" in result.stdout

    # Verify the term is now searchable.
    lookup = runner.invoke(app, ["lib", "lookup", "it"])
    assert lookup.exit_code == 0
    assert "ImportedTerm" in lookup.stdout


def test_lib_import_rejects_non_json(cli_env, tmp_path) -> None:
    bad_path = tmp_path / "junk.json"
    bad_path.write_text("this is not json {{{", encoding="utf-8")
    result = runner.invoke(app, ["lib", "import", str(bad_path)])
    assert result.exit_code == 2


def test_lib_negatives_add_and_list(cli_env) -> None:
    """`lib negatives --add ...` then `lib negatives` (no args, list)."""
    result = runner.invoke(
        app,
        [
            "lib",
            "negatives",
            "--add",
            "其实就是",
            "--not-to",
            "就是",
            "--reason",
            "filler preservation",
        ],
    )
    assert result.exit_code == 0
    assert "added" in result.stdout.lower()

    listing = runner.invoke(app, ["lib", "negatives"])
    assert listing.exit_code == 0
    assert "其实就是" in listing.stdout


def test_lib_negatives_delete_by_id(cli_env) -> None:
    from clearscript.config import load_config
    from clearscript.library import Library

    cfg = load_config()
    lib = Library(cfg.library_path)
    lib.add_negative(text="DeleteMe")
    target_id = lib.list_negatives()[0]["id"]
    lib.close()

    result = runner.invoke(app, ["lib", "negatives", "--delete", str(target_id)])
    assert result.exit_code == 0
    assert "deleted" in result.stdout.lower()


def test_lib_negatives_delete_missing_id_fails(cli_env) -> None:
    result = runner.invoke(app, ["lib", "negatives", "--delete", "99999"])
    assert result.exit_code == 1


def test_lib_health_command(cli_env) -> None:
    """`clearscript lib health` prints a summary even on an empty library."""
    result = runner.invoke(app, ["lib", "health"])
    assert result.exit_code == 0
    assert "Library health" in result.stdout


def test_lib_health_surfaces_duplicate_alias(cli_env) -> None:
    from clearscript.config import load_config
    from clearscript.library import Library

    cfg = load_config()
    lib = Library(cfg.library_path)
    lib.add_term(canonical="Foo", aliases=["shared"])
    lib.add_term(canonical="Bar", aliases=["shared"])
    lib.close()

    result = runner.invoke(app, ["lib", "health"])
    assert result.exit_code == 0
    # Either the alias name itself shows up in the "Duplicate aliases" table,
    # or the summary line shows a non-zero count.
    assert "Duplicate aliases" in result.stdout
    assert "shared" in result.stdout


def test_lib_export_markdown_flag(cli_env, tmp_path) -> None:
    """`clearscript lib export --md` writes a markdown view."""
    from clearscript.config import load_config
    from clearscript.library import Library

    cfg = load_config()
    lib = Library(cfg.library_path)
    lib.add_term(canonical="MarkdownTerm", aliases=["mt"])
    lib.close()

    out = tmp_path / "lib.md"
    result = runner.invoke(app, ["lib", "export", str(out), "--md"])
    assert result.exit_code == 0, result.stdout
    md = out.read_text(encoding="utf-8")
    assert "# clearscript library" in md
    assert "MarkdownTerm" in md


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
