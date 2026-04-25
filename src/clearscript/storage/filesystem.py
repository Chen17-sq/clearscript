"""Project directory layout.

Each project lives under ``<projects_root>/<slug>/``::

    <slug>/
    ├── meta.json              # project metadata
    ├── raw/                   # original uploaded files
    ├── parsed/                # NormalizedTranscript JSON
    ├── working/               # intermediate per-stage artifacts
    ├── final/                 # exported deliverables
    └── changelog.md           # session-end summary

The pipeline reads/writes through ``Project`` so swapping storage backends
later (e.g., S3, encrypted volume) is a single edit.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Project:
    slug: str
    root: Path

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def parsed_dir(self) -> Path:
        return self.root / "parsed"

    @property
    def working_dir(self) -> Path:
        return self.root / "working"

    @property
    def final_dir(self) -> Path:
        return self.root / "final"

    @property
    def meta_path(self) -> Path:
        return self.root / "meta.json"

    def write_meta(self, data: dict[str, object]) -> None:
        self.meta_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def read_meta(self) -> dict[str, object]:
        if not self.meta_path.is_file():
            return {}
        return json.loads(self.meta_path.read_text(encoding="utf-8"))

    def ensure_dirs(self) -> None:
        for d in (self.raw_dir, self.parsed_dir, self.working_dir, self.final_dir):
            d.mkdir(parents=True, exist_ok=True)


class ProjectStore:
    """Locates and creates project directories under a root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def slug_for(self, hint: str) -> str:
        date = dt.date.today().isoformat()
        cleaned = re.sub(r"[^\w一-龥]+", "-", hint.strip()).strip("-").lower()
        if not cleaned:
            cleaned = "transcript"
        return f"{date}-{cleaned}"[:80]

    def create(self, hint: str) -> Project:
        slug = self.slug_for(hint)
        project = Project(slug=slug, root=self.root / slug)
        project.ensure_dirs()
        return project

    def open(self, slug: str) -> Project:
        return Project(slug=slug, root=self.root / slug)
