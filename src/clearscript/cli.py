"""CLI entry point.

::

    clearscript serve [--host 127.0.0.1] [--port 7681] [--no-open]
    clearscript run <input> [--provider claude] [--model claude-opus-4-7] [--out path]
    clearscript providers
    clearscript lib stats
    clearscript projects list
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
from clearscript.storage import ProjectStore

app = typer.Typer(
    name="clearscript",
    help="Local-first ASR transcript editor. Bring your own model.",
    no_args_is_help=True,
    add_completion=False,
)
lib_app = typer.Typer(name="lib", help="Library inspection and management.", no_args_is_help=True)
app.add_typer(lib_app, name="lib")
projects_app = typer.Typer(
    name="projects", help="Project history (every Run is auto-saved here).", no_args_is_help=True
)
app.add_typer(projects_app, name="projects")

console = Console()
err_console = Console(stderr=True)


@app.command()
def version() -> None:
    """Show version."""
    console.print(f"clearscript [bold]{__version__}[/bold]")


@app.command()
def serve(
    host: str = typer.Option(
        "127.0.0.1", "--host", "-h", help="Host to bind. Default 127.0.0.1 (local only)."
    ),
    port: int = typer.Option(7681, "--port", "-P", help="Port to listen on."),
    no_open: bool = typer.Option(False, "--no-open", help="Don't auto-open the browser."),
) -> None:
    """Start the local web UI at http://127.0.0.1:7681 (default)."""
    from clearscript.server import serve as run_server

    console.print(f"[bold]clearscript[/bold] [dim]v{__version__}[/dim]")
    console.print(f"Open in your browser: [bold]http://{host}:{port}[/bold]")
    console.print("Press Ctrl+C to stop.\n")
    try:
        run_server(host=host, port=port, open_browser=not no_open)
    except KeyboardInterrupt:
        console.print("\n[dim]Server stopped.[/dim]")


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


@app.command("set-key")
def set_key(
    provider: str = typer.Argument(..., help="Provider name (claude / openai / deepseek / gemini)"),
    api_key: str | None = typer.Argument(
        None,
        help="API key (omit to be prompted securely so the key isn't in shell history)",
    ),
    delete: bool = typer.Option(False, "--delete", help="Remove the stored key instead"),
) -> None:
    """Store a provider's API key in your OS keyring.

    Cross-platform: macOS Keychain, Windows Credential Manager, Linux
    Secret Service. The key survives reboots and is never written to
    disk by clearscript. Removes the need to ``export SOMETHING_API_KEY``
    in your shell config.

    Examples:
        clearscript set-key claude              # prompts for key
        clearscript set-key deepseek sk-...     # inline (avoid in shared terminals)
        clearscript set-key claude --delete     # remove stored key
    """
    cfg = load_config()
    if provider not in cfg.providers:
        err_console.print(
            f"[red]Unknown provider {provider!r}. Available: {list(cfg.providers.keys())}[/red]"
        )
        raise typer.Exit(2)
    try:
        import keyring
    except ImportError as exc:
        err_console.print(
            "[red]keyring package not available. "
            "Install with: uv pip install keyring[/red]"
        )
        raise typer.Exit(2) from exc

    if delete:
        try:
            keyring.delete_password("clearscript", provider)
            console.print(f"[green]✓[/green] deleted stored key for {provider}")
        except keyring.errors.PasswordDeleteError:
            console.print(f"[dim]No stored key for {provider} (already gone)[/dim]")
        return

    if not api_key:
        api_key = typer.prompt(f"API key for {provider}", hide_input=True)
    api_key = (api_key or "").strip()
    if not api_key:
        err_console.print("[red]Empty key — aborting[/red]")
        raise typer.Exit(2)

    try:
        keyring.set_password("clearscript", provider, api_key)
    except Exception as exc:
        err_console.print(f"[red]Failed to save to keyring: {exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(
        f"[green]✓[/green] saved key for {provider} to keyring "
        f"(service=clearscript, account={provider})"
    )


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


@projects_app.command("list")
def projects_list(
    limit: int = typer.Option(50, "--limit", "-n", help="Max number of runs to show"),
) -> None:
    """List saved project runs, newest first."""
    cfg = load_config()
    ensure_dirs(cfg)
    store = ProjectStore(cfg.projects_root)
    rows = store.list_summaries(limit=limit)

    if not rows:
        console.print(
            f"[dim]No saved runs yet. Projects are saved to {cfg.projects_root} after each Run.[/dim]"
        )
        return

    table = Table(title=f"Project history · {len(rows)} runs ({cfg.projects_root})")
    table.add_column("Created", style="bold")
    table.add_column("Slug", overflow="fold")
    table.add_column("Title", overflow="fold")
    table.add_column("Format")
    table.add_column("Model", overflow="fold")
    table.add_column("Tokens", justify="right")
    table.add_column("Changes", justify="right")
    for r in rows:
        created = (r.get("created_at") or "").replace("T", " ")[:16]
        table.add_row(
            created,
            r["slug"],
            r.get("title") or "—",
            (r.get("format") or "—").upper(),
            r.get("model") or "—",
            str(r.get("total_tokens") or 0),
            str(r.get("change_count") or 0),
        )
    console.print(table)


@projects_app.command("show")
def projects_show(
    slug: str = typer.Argument(..., help="Project slug from `projects list`"),
    json_out: bool = typer.Option(False, "--json", help="Print raw JSON detail"),
) -> None:
    """Show the cleaned transcript and meta for one saved run."""
    cfg = load_config()
    ensure_dirs(cfg)
    store = ProjectStore(cfg.projects_root)
    if not store.exists(slug):
        err_console.print(f"[red]Project {slug!r} not found in {cfg.projects_root}[/red]")
        raise typer.Exit(1)

    detail = store.open(slug).detail()
    if json_out:
        console.print_json(json.dumps(detail, ensure_ascii=False))
        return

    console.print(f"[bold]Slug:[/bold]    {detail.get('slug')}")
    console.print(f"[bold]Title:[/bold]   {detail.get('title') or '—'}")
    console.print(f"[bold]Created:[/bold] {detail.get('created_at') or '—'}")
    console.print(f"[bold]Provider:[/bold] {detail.get('provider')} · model: {detail.get('model')}")
    console.print(
        f"[bold]Tokens:[/bold]  {detail.get('total_tokens')} (in={detail.get('input_tokens')} out={detail.get('output_tokens')})"
    )
    console.print(f"[bold]Changes:[/bold] {len(detail.get('change_log') or [])}")
    console.print(f"[bold]Suggestions:[/bold] {len(detail.get('suggestions') or [])}")
    console.print()
    console.print(
        "[bold]Cleaned transcript[/bold] [dim]({} chars)[/dim]:".format(
            len(detail.get("cleaned_markdown") or "")
        )
    )
    console.print(detail.get("cleaned_markdown") or "(empty)")


@projects_app.command("delete")
def projects_delete(
    slug: str = typer.Argument(..., help="Project slug to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Permanently delete a saved run."""
    cfg = load_config()
    ensure_dirs(cfg)
    store = ProjectStore(cfg.projects_root)
    if not store.exists(slug):
        err_console.print(f"[red]Project {slug!r} not found[/red]")
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(f"Delete project {slug!r}? This is permanent.")
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            return

    store.delete(slug)
    console.print(f"[green]✓[/green] deleted {slug}")


@projects_app.command("path")
def projects_path() -> None:
    """Print the projects root directory."""
    cfg = load_config()
    console.print(str(cfg.projects_root))


@projects_app.command("rerun")
def projects_rerun(
    slug: str = typer.Argument(..., help="Project slug to re-run"),
    provider: str | None = typer.Option(
        None, "--provider", "-p", help="Provider override (default: original project's)"
    ),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Model override (default: original project's)"
    ),
) -> None:
    """Re-run a saved project against the *current* library.

    Use this after you've added or corrected terms in the library — the
    rerun captures the improved output as a new sibling project so you
    can diff the two runs and see what changed.
    """
    from clearscript.ingest.json_ingest import JsonAdapter
    from clearscript.ingest.md import MdAdapter
    from clearscript.ingest.srt import SrtAdapter
    from clearscript.ingest.txt import TxtAdapter
    from clearscript.ingest.vtt import VttAdapter

    cfg = load_config()
    ensure_dirs(cfg)
    store = ProjectStore(cfg.projects_root)
    if not store.exists(slug):
        err_console.print(f"[red]Project {slug!r} not found[/red]")
        raise typer.Exit(1)

    orig = store.open(slug)
    orig_meta = orig.read_meta()
    input_pair = orig.read_input()
    if input_pair is None:
        err_console.print(
            f"[red]Cannot re-run {slug!r}: original input is binary or unreadable. "
            "Run `clearscript run` against the source file again instead.[/red]"
        )
        raise typer.Exit(2)

    input_text, fmt = input_pair
    briefing_text = orig.read_briefing()

    chosen_provider_name = provider or orig_meta.get("provider")
    try:
        provider_cfg = cfg.get_provider(chosen_provider_name)
    except KeyError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc

    chosen_model = model or orig_meta.get("model") or provider_cfg.default_model
    if not chosen_model:
        err_console.print("[red]No model resolved for rerun — pass --model[/red]")
        raise typer.Exit(2)

    try:
        llm = build_provider(provider_cfg)
    except RuntimeError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc

    adapters = {
        "txt": TxtAdapter,
        "md": MdAdapter,
        "srt": SrtAdapter,
        "vtt": VttAdapter,
        "json": JsonAdapter,
    }
    adapter_cls = adapters.get(fmt, TxtAdapter)
    try:
        transcript_obj = adapter_cls().parse_string(input_text)
    except ValueError as exc:
        err_console.print(f"[red]Failed to parse stored input: {exc}[/red]")
        raise typer.Exit(2) from exc

    library = Library(cfg.library_path)
    pipeline = Pipeline(
        provider=llm,
        model=chosen_model,
        library=library,
        briefing_context=briefing_text,
    )

    console.print(f"[bold]Re-running:[/bold] {slug}")
    console.print(f"[bold]Provider:[/bold]   {chosen_provider_name} · model {chosen_model}")
    console.print()

    try:
        result = pipeline.run_on_transcript(transcript_obj)
    except Exception as exc:
        err_console.print(f"[red]Pipeline failed: {exc}[/red]")
        raise typer.Exit(1) from exc
    finally:
        library.close()

    new_project = store.create_rerun_of(slug)
    new_project.save_run(
        title=orig_meta.get("title"),
        format_=fmt,
        provider=result.provider,
        model=result.model,
        input_text=input_text,
        briefing=briefing_text,
        edited_markdown=result.edited_markdown,
        change_log=result.change_log,
        suggestions=result.suggestions,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    meta = new_project.read_meta()
    meta["rerun_of"] = slug
    new_project.write_meta(meta)

    console.print(f"[green]✓[/green] new project: {new_project.slug}")
    console.print(f"[dim]changes: {len(result.change_log)} · "
                  f"tokens: in={result.input_tokens} out={result.output_tokens}[/dim]")


@lib_app.command("negatives")
def lib_negatives(
    add: str | None = typer.Option(
        None, "--add", help="Add a new negative rule (the text NOT to change)"
    ),
    do_not_change_to: str | None = typer.Option(
        None, "--not-to", help="With --add: the wrong target the model keeps choosing"
    ),
    domain: str | None = typer.Option(None, "--domain", help="Optional domain scope"),
    reason: str | None = typer.Option(None, "--reason", help="Why this rule exists"),
    delete: int | None = typer.Option(
        None, "--delete", help="Delete a negative rule by id (use `lib negatives` to list)"
    ),
) -> None:
    """List, add, or delete negative-correction rules.

    Negatives tell L3 'do NOT change X' even when the model thinks it
    should. Examples: keep speaker colloquialisms ("蛮好的" not "很好"),
    preserve approximate phrasing ("差不多三四百人").

    With no flags, lists existing negatives.
    """
    cfg = load_config()
    ensure_dirs(cfg)
    library = Library(cfg.library_path)
    try:
        if add:
            library.add_negative(
                text=add,
                do_not_change_to=do_not_change_to,
                domain=domain,
                reason=reason,
            )
            console.print(f"[green]✓[/green] added negative rule: don't change {add!r}")
            return
        if delete is not None:
            ok = library.delete_negative(delete)
            if ok:
                console.print(f"[green]✓[/green] deleted negative rule #{delete}")
            else:
                err_console.print(f"[red]No negative rule with id {delete}[/red]")
                raise typer.Exit(1)
            return

        rows = library.list_negatives()
    finally:
        library.close()

    if not rows:
        console.print("[dim]No negative rules. Add one with `lib negatives --add ...`[/dim]")
        return
    table = Table(title="Negative-correction rules")
    table.add_column("ID")
    table.add_column("Text", style="bold")
    table.add_column("Don't change to")
    table.add_column("Domain")
    table.add_column("Reason", overflow="fold")
    for r in rows:
        table.add_row(
            str(r["id"]),
            r["text"],
            r.get("do_not_change_to") or "—",
            r.get("domain") or "—",
            r.get("reason") or "—",
        )
    console.print(table)


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


@lib_app.command("search")
def lib_search(
    query: str = typer.Argument(..., help="Substring or alias to search for"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
) -> None:
    """Full-text search across the term library (FTS5-backed).

    Unlike ``lib lookup`` which is an exact alias match, search runs an
    FTS query so partial matches and typos surface useful hits.
    """
    cfg = load_config()
    ensure_dirs(cfg)
    library = Library(cfg.library_path)
    try:
        hits = library.search_terms(query, limit=limit)
    finally:
        library.close()
    if not hits:
        console.print(f"[dim]No matches for {query!r}[/dim]")
        return
    table = Table(title=f"Library search: {query!r}")
    table.add_column("Canonical", style="bold")
    table.add_column("Type")
    table.add_column("Domain")
    table.add_column("Confidence", justify="right")
    for h in hits:
        table.add_row(
            h.canonical,
            h.type or "—",
            h.domain or "—",
            f"{h.confidence:.2f}",
        )
    console.print(table)


@lib_app.command("export")
def lib_export(
    out_path: Path = typer.Argument(
        ..., help="Where to write the library export (e.g. ./my-library.json)"
    ),
    as_markdown: bool = typer.Option(
        False, "--md", help="Write a human-readable markdown view instead of JSON"
    ),
) -> None:
    """Export the entire library for backup or sharing.

    By default writes the versioned JSON that ``lib import`` can re-ingest.
    Pass ``--md`` for a git-friendly markdown view (read-only — not
    importable, just for reading and diffing in a repo).
    """
    cfg = load_config()
    ensure_dirs(cfg)
    library = Library(cfg.library_path)
    try:
        if as_markdown:
            content = library.export_markdown()
            out_path.write_text(content, encoding="utf-8")
            console.print(f"[green]✓[/green] wrote library markdown → {out_path}")
            return
        payload = library.export_dict()
    finally:
        library.close()
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    console.print(f"[green]✓[/green] wrote library export → {out_path}")
    console.print(
        f"[dim]terms: {len(payload['terms'])} · speakers: {len(payload['speakers'])} · "
        f"patterns: {len(payload['edit_patterns'])} · negatives: {len(payload['negatives'])}[/dim]"
    )


@lib_app.command("health")
def lib_health(
    stale_days: int = typer.Option(
        90, "--stale-days", help="Days since last use to count a term as stale"
    ),
) -> None:
    """Report library health — duplicates, low-confidence, stale terms.

    Run this periodically (or after a busy Mode B harvest) to keep the
    library tidy. Use the IDs in the output with ``lib delete-term`` or
    the web UI's library tab.
    """
    cfg = load_config()
    ensure_dirs(cfg)
    library = Library(cfg.library_path)
    try:
        report = library.health_check(stale_days=stale_days)
    finally:
        library.close()

    summary = report["summary"]
    console.print(
        f"[bold]Library health[/bold] (stale threshold: {report['stale_days_threshold']} days)\n"
    )
    console.print(f"  Duplicate aliases:     {summary['duplicate_alias_groups']}")
    console.print(f"  Duplicate canonicals:  {summary['duplicate_canonical_groups']}")
    console.print(f"  Low-confidence terms:  {summary['low_confidence_count']}")
    console.print(f"  Stale terms:           {summary['stale_count']}")
    console.print(f"  Orphan aliases:        {summary['orphan_alias_count']}")
    console.print()

    if report["duplicate_aliases"]:
        t = Table(title="Duplicate aliases (one alias → multiple canonicals)")
        t.add_column("Alias", style="bold")
        t.add_column("Maps to")
        t.add_column("Count", justify="right")
        for d in report["duplicate_aliases"][:20]:
            t.add_row(d["alias"], d["canonicals"], str(d["n"]))
        console.print(t)

    if report["duplicate_canonicals"]:
        t = Table(title="Duplicate canonicals")
        t.add_column("Canonical", style="bold")
        t.add_column("Times added", justify="right")
        for d in report["duplicate_canonicals"][:20]:
            t.add_row(d["canonical"], str(d["n"]))
        console.print(t)

    if report["low_confidence_terms"]:
        t = Table(title="Low-confidence terms (< 0.3)")
        t.add_column("ID")
        t.add_column("Canonical", style="bold")
        t.add_column("Type")
        t.add_column("Confidence", justify="right")
        for d in report["low_confidence_terms"][:20]:
            t.add_row(
                str(d["id"]),
                d["canonical"],
                d.get("type") or "—",
                f"{d['confidence']:.2f}",
            )
        console.print(t)


@lib_app.command("import")
def lib_import(
    in_path: Path = typer.Argument(
        ..., exists=True, readable=True, help="Path to a library export JSON"
    ),
) -> None:
    """Merge a library JSON export into the local library.

    Existing terms with a matching canonical have their aliases extended;
    new terms are inserted. Speakers, patterns, and negatives are merged
    with the same union semantics.
    """
    cfg = load_config()
    ensure_dirs(cfg)
    try:
        payload = json.loads(in_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        err_console.print(f"[red]Failed to read {in_path}: {exc}[/red]")
        raise typer.Exit(2) from exc

    library = Library(cfg.library_path)
    try:
        try:
            summary = library.import_dict(payload)
        except ValueError as exc:
            err_console.print(f"[red]{exc}[/red]")
            raise typer.Exit(2) from exc
    finally:
        library.close()

    console.print(f"[green]✓[/green] imported {in_path}")
    for k, v in summary.items():
        console.print(f"  {k}: {v}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
