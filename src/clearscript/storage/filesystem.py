"""Project directory layout.

Each project lives under ``<projects_root>/<slug>/``::

    <slug>/
    ├── meta.json            # project metadata + run summary
    ├── raw/
    │   └── input.<ext>      # original uploaded text/file (verbatim)
    ├── briefing.txt         # if briefing was provided
    ├── final/
    │   ├── transcript.md    # cleaned output
    │   └── transcript.docx  # generated on demand
    ├── change_log.json      # every edit the model made
    └── suggestions.json     # Mode B library suggestions

The pipeline writes through ``Project.save_run`` so swapping storage backends
later (encrypted volume, S3, etc.) is a single edit.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

_SLUG_TIME_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{6}-")


@dataclass
class Project:
    slug: str
    root: Path

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def final_dir(self) -> Path:
        return self.root / "final"

    @property
    def meta_path(self) -> Path:
        return self.root / "meta.json"

    @property
    def change_log_path(self) -> Path:
        return self.root / "change_log.json"

    @property
    def suggestions_path(self) -> Path:
        return self.root / "suggestions.json"

    @property
    def briefing_path(self) -> Path:
        return self.root / "briefing.txt"

    @property
    def cleaned_md_path(self) -> Path:
        return self.final_dir / "transcript.md"

    @property
    def cleaned_docx_path(self) -> Path:
        return self.final_dir / "transcript.docx"

    def write_meta(self, data: dict) -> None:
        self.meta_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def read_meta(self) -> dict:
        if not self.meta_path.is_file():
            return {}
        return json.loads(self.meta_path.read_text(encoding="utf-8"))

    def ensure_dirs(self) -> None:
        for d in (self.raw_dir, self.final_dir):
            d.mkdir(parents=True, exist_ok=True)

    def save_run(
        self,
        *,
        title: str | None,
        format_: str,
        provider: str,
        model: str,
        input_text: str | None = None,
        input_bytes: bytes | None = None,
        input_filename: str | None = None,
        briefing: str | None = None,
        edited_markdown: str,
        change_log: list,
        suggestions: list,
        input_tokens: int,
        output_tokens: int,
        duration_sec: float | None = None,
    ) -> None:
        """Persist a single pipeline run as the project's content."""
        self.ensure_dirs()

        ext = (format_ or "txt").lower()
        if ext == "json" or ext == "txt" or ext == "md" or ext == "srt" or ext == "vtt":
            input_name = f"input.{ext}"
        else:
            input_name = input_filename or f"input.{ext}"
        input_path = self.raw_dir / input_name
        if input_bytes is not None:
            input_path.write_bytes(input_bytes)
        elif input_text is not None:
            input_path.write_text(input_text, encoding="utf-8")

        if briefing:
            self.briefing_path.write_text(briefing, encoding="utf-8")

        if title:
            md = f"# {title}\n\n{edited_markdown.strip()}\n"
        else:
            md = edited_markdown.strip() + "\n"
        self.cleaned_md_path.write_text(md, encoding="utf-8")

        self.change_log_path.write_text(
            json.dumps(change_log, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.suggestions_path.write_text(
            json.dumps(suggestions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.write_meta(
            {
                "slug": self.slug,
                "title": title,
                "format": ext,
                "provider": provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "change_count": len(change_log),
                "suggestion_count": len(suggestions),
                "duration_sec": duration_sec,
                "created_at": dt.datetime.now().isoformat(timespec="seconds"),
                "input_filename": input_name,
            }
        )

    def summary(self) -> dict:
        """Return a flat summary dict suitable for list views."""
        meta = self.read_meta()
        return {
            "slug": self.slug,
            "title": meta.get("title"),
            "format": meta.get("format"),
            "provider": meta.get("provider"),
            "model": meta.get("model"),
            "input_tokens": meta.get("input_tokens", 0),
            "output_tokens": meta.get("output_tokens", 0),
            "total_tokens": meta.get("total_tokens", 0),
            "change_count": meta.get("change_count", 0),
            "suggestion_count": meta.get("suggestion_count", 0),
            "duration_sec": meta.get("duration_sec"),
            "created_at": meta.get("created_at"),
            # When this project is a rerun, expose the original slug so the
            # UI can render a "↻ rerun of X" badge.
            "rerun_of": meta.get("rerun_of"),
        }

    def detail(self) -> dict:
        """Full payload for the detail panel: meta + cleaned md + changelog + suggestions + briefing."""
        meta = self.read_meta()
        cleaned_md = (
            self.cleaned_md_path.read_text(encoding="utf-8")
            if self.cleaned_md_path.is_file()
            else ""
        )
        change_log = (
            json.loads(self.change_log_path.read_text(encoding="utf-8"))
            if self.change_log_path.is_file()
            else []
        )
        suggestions = (
            json.loads(self.suggestions_path.read_text(encoding="utf-8"))
            if self.suggestions_path.is_file()
            else []
        )
        briefing = (
            self.briefing_path.read_text(encoding="utf-8") if self.briefing_path.is_file() else ""
        )
        # Best-effort raw input
        raw_input = ""
        for p in self.raw_dir.glob("input.*"):
            try:
                raw_input = p.read_text(encoding="utf-8")
                break
            except (UnicodeDecodeError, OSError):
                # binary (e.g. .docx) — skip in detail; client downloads separately
                break

        return {
            **meta,
            "cleaned_markdown": cleaned_md,
            "change_log": change_log,
            "suggestions": suggestions,
            "briefing": briefing,
            "raw_input": raw_input,
        }

    def delete(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def read_input(self) -> tuple[str, str] | None:
        """Read the raw input text + format extension back.

        Returns ``None`` for binary inputs (e.g. .docx) or missing files —
        rerun is only meaningful when we can replay the original text.
        """
        for p in self.raw_dir.glob("input.*"):
            ext = p.suffix.lstrip(".")
            try:
                return p.read_text(encoding="utf-8"), ext
            except (UnicodeDecodeError, OSError):
                return None
        return None

    def read_briefing(self) -> str:
        if self.briefing_path.is_file():
            return self.briefing_path.read_text(encoding="utf-8")
        return ""


class ProjectStore:
    """Locates and creates project directories under a root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def slug_for(self, hint: str) -> str:
        """Build a slug like ``2026-04-25-143012-acme-cto-interview``.

        Includes seconds-precision so two runs in the same minute don't collide.
        """
        now = dt.datetime.now()
        timestamp = now.strftime("%Y-%m-%d-%H%M%S")
        cleaned = re.sub(r"[^\w一-龥]+", "-", hint.strip()).strip("-").lower()
        if not cleaned:
            cleaned = "transcript"
        return f"{timestamp}-{cleaned}"[:80]

    def create(self, hint: str) -> Project:
        slug = self.slug_for(hint)
        project = Project(slug=slug, root=self.root / slug)
        project.ensure_dirs()
        return project

    def open(self, slug: str) -> Project:
        return Project(slug=slug, root=self.root / slug)

    def create_rerun_of(self, orig_slug: str) -> Project:
        """Create a sibling project for a re-run, with a stable suffix.

        The new slug retains the meaningful tail of the original (everything
        after the timestamp prefix) plus ``-rerun`` — e.g.
        ``2026-05-16-143012-acme-cto`` → ``2026-05-16-150455-acme-cto-rerun``.
        """
        tail = _SLUG_TIME_PREFIX.sub("", orig_slug)
        hint = f"{tail}-rerun"
        return self.create(hint)

    def exists(self, slug: str) -> bool:
        return (self.root / slug / "meta.json").is_file()

    def list_summaries(self, *, limit: int = 200) -> list[dict]:
        """Return all projects sorted newest-first."""
        candidates: list[Project] = []
        for sub in self.root.iterdir():
            if not sub.is_dir():
                continue
            if not (sub / "meta.json").is_file():
                continue
            candidates.append(Project(slug=sub.name, root=sub))

        # Sort by created_at from meta (fallback to slug timestamp prefix)
        def sort_key(p: Project) -> str:
            meta = p.read_meta()
            return str(meta.get("created_at") or p.slug)

        candidates.sort(key=sort_key, reverse=True)
        return [p.summary() for p in candidates[:limit]]

    def delete(self, slug: str) -> bool:
        if not self.exists(slug):
            return False
        Project(slug=slug, root=self.root / slug).delete()
        return True
