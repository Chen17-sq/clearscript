"""CLI entry point.

::

    clearscript run <input> [--provider claude] [--model claude-opus-4-7] [--out path]
    clearscript providers
    clearscript lib stats
    clearscript version
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from clearscript import __version__
from clearscript.config import ensure_dirs, load_config
from clearscript.core.pipeline import Pipeline
from clearscript.export import write_docx, write_markdown
from clearscript.library import Library
from clearscript.providers import build_provider

app = typer.Typer(
    name="clearscript",
    help="Local-first ASR transcript editor. Bring your own model.",
    no_args_is_help=True,
    add_completion=False,
)
lib_app = typer.Typer(name="lib", help="Library inspection and management.", no_args_is_help=True)
app.add_typer(lib_app, name="lib")

console = Console()
err_console = Console(stderr=True)


@app.command()
def version() -> None:
    """Show version."""
    console.print(f"clearscript [bold]{__version__}[/bold]")


@app.command()
def providers() -> None:
    """List configured providers."""
    cfg = load_config()
    table = Table(title="Configured providers", show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Default model")
    table.add_column("Has key?")
    table.add_column("Base URL")
    for name, p in cfg.providers.items():
        has_key = "✓" if p.resolve_api_key() else "✗"
        if p.type == "ollama":
            has_key = "n/a"
        table.add_row(name, p.type, p.default_model or "—", has_key, p.base_url or "—")
    console.print(table)
    console.print()
    console.print(f"Default provider: [bold]{cfg.default_provider}[/bold]")


@app.command()
def run(
    input_path: Path = typer.Argument(
        ..., exists=True, readable=True, help="Input ASR transcript file"
    ),
    provider: str | None = typer.Option(
        None, "--provider", "-p", help="Provider name (defaults to config default)"
    ),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Model id (defaults to provider default)"
    ),
    output: Path | None = typer.Option(
        None, "--out", "-o", help="Output markdown path (default: <input>.cleaned.md)"
    ),
    docx_out: Path | None = typer.Option(None, "--docx", help="Also write a .docx to this path"),
    title: str | None = typer.Option(
        None, "--title", help="Title to put at the top of the deliverable"
    ),
    briefing: Path | None = typer.Option(
        None, "--briefing", help="Path to a context-briefing markdown file"
    ),
    no_library: bool = typer.Option(False, "--no-library", help="Skip library lookup for this run"),
) -> None:
    """Run the editing pipeline on a single input file."""
    cfg = load_config()
    ensure_dirs(cfg)

    try:
        provider_cfg = cfg.get_provider(provider)
    except KeyError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc

    chosen_model = model or provider_cfg.default_model
    if not chosen_model:
        err_console.print(
            f"[red]No model specified and provider {provider_cfg.name!r} has no default. "
            "Pass --model.[/red]"
        )
        raise typer.Exit(2)

    try:
        llm = build_provider(provider_cfg)
    except RuntimeError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc

    library: Library | None = None
    if not no_library:
        library = Library(cfg.library_path)

    briefing_text = ""
    if briefing and briefing.is_file():
        briefing_text = briefing.read_text(encoding="utf-8")

    pipeline = Pipeline(
        provider=llm,
        model=chosen_model,
        library=library,
        briefing_context=briefing_text,
    )

    console.print(f"[bold]Provider:[/bold] {provider_cfg.name} ([dim]{provider_cfg.type}[/dim])")
    console.print(f"[bold]Model:[/bold]    {chosen_model}")
    console.print(f"[bold]Input:[/bold]    {input_path}")
    console.print()
    console.print("Running edit pipeline (this may take a minute for long transcripts)...")
    console.print()

    try:
        result = pipeline.run(input_path)
    except Exception as exc:
        err_console.print(f"[red]Pipeline failed: {exc}[/red]")
        raise typer.Exit(1) from exc
    finally:
        if library:
            library.close()

    md_out = output or input_path.with_suffix(".cleaned.md")
    write_markdown(result.edited_markdown, md_out, title=title)
    console.print(f"[green]✓[/green] markdown → {md_out}")

    if docx_out:
        try:
            write_docx(result.edited_markdown, docx_out, title=title)
            console.print(f"[green]✓[/green] docx     → {docx_out}")
        except Exception as exc:
            err_console.print(f"[yellow]docx export failed: {exc}[/yellow]")

    log_path = md_out.with_suffix(".changelog.json")
    log_path.write_text(
        json.dumps(result.change_log, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    console.print(f"[green]✓[/green] log      → {log_path}")

    console.print()
    console.print(
        f"[dim]tokens: in={result.input_tokens} out={result.output_tokens} "
        f"total={result.total_tokens}[/dim]"
    )
    console.print(f"[dim]changes: {len(result.change_log)}[/dim]")


@lib_app.command("stats")
def lib_stats() -> None:
    """Show library statistics."""
    cfg = load_config()
    ensure_dirs(cfg)
    library = Library(cfg.library_path)
    try:
        stats = library.stats()
    finally:
        library.close()

    table = Table(title=f"Library: {cfg.library_path}")
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    for key, value in stats.items():
        table.add_row(key, str(value))
    console.print(table)


@lib_app.command("add-term")
def lib_add_term(
    canonical: str = typer.Argument(..., help="Canonical form, e.g. 'Dify'"),
    aliases: str | None = typer.Option(None, "--aliases", help="Comma-separated ASR variants"),
    type_: str | None = typer.Option(
        None, "--type", help="company / product / acronym / jargon / person"
    ),
    domain: str | None = typer.Option(None, "--domain", help="vc / ai-infra / medical / ..."),
    definition: str | None = typer.Option(None, "--def", help="Optional definition"),
) -> None:
    """Add a term to the library."""
    cfg = load_config()
    ensure_dirs(cfg)
    alias_list = [a.strip() for a in aliases.split(",") if a.strip()] if aliases else []
    library = Library(cfg.library_path)
    try:
        term_id = library.add_term(
            canonical=canonical,
            aliases=alias_list,
            type_=type_,
            domain=domain,
            definition=definition,
        )
    finally:
        library.close()
    console.print(
        f"[green]✓[/green] term {canonical!r} stored (id={term_id}, aliases={alias_list})"
    )


@lib_app.command("lookup")
def lib_lookup(
    alias: str = typer.Argument(..., help="ASR variant or canonical to look up"),
) -> None:
    """Look up a term by alias."""
    cfg = load_config()
    ensure_dirs(cfg)
    library = Library(cfg.library_path)
    try:
        hit = library.lookup_alias(alias)
    finally:
        library.close()
    if hit:
        console.print(
            f"[bold]{hit.alias}[/bold] → [green]{hit.canonical}[/green] (confidence {hit.confidence:.2f}, domain={hit.domain or '—'})"
        )
    else:
        console.print(f"[dim]No match for {alias!r}[/dim]")
        sys.exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
