"""SQLite-backed terminology library.

v0.0.1 implements the foundational read/write paths needed by the minimum
happy path. The schema (``schema.sql``) already defines everything required
for the v0.1 features so future code only needs to grow callers, not the
storage layer.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


@dataclass
class TermHit:
    canonical: str
    alias: str
    confidence: float
    domain: str | None
    type: str | None


@dataclass
class SpeakerHit:
    canonical_name: str
    display_label: str
    matched_alias: str


class Library:
    """Local SQLite library for terms, speakers, edit patterns, and sessions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self) -> None:
        schema = (
            resources.files("clearscript.library")
            .joinpath("schema.sql")
            .read_text(encoding="utf-8")
        )
        self._conn.executescript(schema)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self._conn.execute("BEGIN")
            yield self._conn
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # --- Terms ---

    def add_term(
        self,
        canonical: str,
        *,
        type_: str | None = None,
        domain: str | None = None,
        aliases: list[str] | None = None,
        definition: str | None = None,
        scope: str = "library",
    ) -> int:
        """Insert a term (or return existing id), then add aliases."""
        row = self._conn.execute(
            "SELECT id FROM terms WHERE canonical = ? AND scope = ?",
            (canonical, scope),
        ).fetchone()
        if row:
            term_id = row["id"]
        else:
            cur = self._conn.execute(
                """
                INSERT INTO terms (canonical, type, domain, definition, scope)
                VALUES (?, ?, ?, ?, ?)
                """,
                (canonical, type_, domain, definition, scope),
            )
            term_id = cur.lastrowid

        for alias in aliases or []:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO term_aliases (term_id, alias, alias_type)
                VALUES (?, ?, ?)
                """,
                (term_id, alias, "asr-error"),
            )
        return int(term_id)

    def confirm_term(self, term_id: int) -> None:
        self._conn.execute(
            """
            UPDATE terms
            SET confirm_count = confirm_count + 1,
                times_used = times_used + 1,
                last_used_at = CURRENT_TIMESTAMP,
                status = CASE
                    WHEN confirm_count + 1 >= 3 THEN 'verified'
                    WHEN confirm_count + 1 >= 1 THEN 'confirmed'
                    ELSE status
                END,
                confidence = MIN(1.0, confidence + 0.1),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (term_id,),
        )

    def reject_term(self, term_id: int) -> None:
        """Mark a term as rejected — increments reject_count, lowers confidence,
        and flips status to 'deprecated' so subsequent lookups + library-context
        injection skip it.

        Rejection is treated as an explicit user signal: one rejection is
        enough to deprecate. ``all_terms_in_domain`` filters by
        ``status != 'deprecated'`` so the rejected term stops showing up in
        the system prompt. The row is preserved (not deleted) so the user
        can un-reject via ``confirm_term`` if they change their mind.
        """
        self._conn.execute(
            """
            UPDATE terms
            SET reject_count = reject_count + 1,
                confidence = MAX(0.0, confidence - 0.2),
                status = 'deprecated',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (term_id,),
        )

    def lookup_alias(self, alias: str) -> TermHit | None:
        """Look up a term by ASR-variant alias OR by canonical form.

        Mode A queries this with whatever entity tokens it finds in the briefing,
        which may be either the user-known canonical (e.g. "Dify") or an ASR
        variant the user remembers (e.g. "DeFi"). We accept both.
        """
        row = self._conn.execute(
            """
            SELECT t.canonical, ta.alias, t.confidence, t.domain, t.type
            FROM term_aliases ta
            JOIN terms t ON t.id = ta.term_id
            WHERE ta.alias = ?
            ORDER BY t.confidence DESC
            LIMIT 1
            """,
            (alias,),
        ).fetchone()
        if row:
            return TermHit(
                canonical=row["canonical"],
                alias=row["alias"],
                confidence=row["confidence"],
                domain=row["domain"],
                type=row["type"],
            )

        canonical_row = self._conn.execute(
            "SELECT canonical, confidence, domain, type FROM terms WHERE canonical = ? ORDER BY confidence DESC LIMIT 1",
            (alias,),
        ).fetchone()
        if canonical_row:
            return TermHit(
                canonical=canonical_row["canonical"],
                alias=alias,
                confidence=canonical_row["confidence"],
                domain=canonical_row["domain"],
                type=canonical_row["type"],
            )
        return None

    def search_terms(self, query: str, limit: int = 20) -> list[TermHit]:
        rows = self._conn.execute(
            """
            SELECT t.canonical, '' AS alias, t.confidence, t.domain, t.type
            FROM terms_fts f
            JOIN terms t ON t.id = f.rowid
            WHERE terms_fts MATCH ?
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
        return [
            TermHit(
                canonical=r["canonical"],
                alias=r["alias"],
                confidence=r["confidence"],
                domain=r["domain"],
                type=r["type"],
            )
            for r in rows
        ]

    def all_terms_in_domain(self, domain: str | None) -> list[TermHit]:
        if domain is None:
            rows = self._conn.execute(
                "SELECT canonical, '' as alias, confidence, domain, type FROM terms WHERE status != 'deprecated'"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT canonical, '' as alias, confidence, domain, type FROM terms WHERE domain IS NULL OR domain = ? AND status != 'deprecated'",
                (domain,),
            ).fetchall()
        return [
            TermHit(
                canonical=r["canonical"],
                alias=r["alias"],
                confidence=r["confidence"],
                domain=r["domain"],
                type=r["type"],
            )
            for r in rows
        ]

    # --- Speakers ---

    def add_speaker(
        self,
        canonical_name: str,
        display_label: str,
        aliases: list[str] | None = None,
        primary_language: str | None = None,
    ) -> int:
        row = self._conn.execute(
            "SELECT id FROM speakers WHERE canonical_name = ?",
            (canonical_name,),
        ).fetchone()
        if row:
            speaker_id = row["id"]
        else:
            cur = self._conn.execute(
                """
                INSERT INTO speakers (canonical_name, display_label, primary_language)
                VALUES (?, ?, ?)
                """,
                (canonical_name, display_label, primary_language),
            )
            speaker_id = cur.lastrowid

        for alias in aliases or []:
            self._conn.execute(
                "INSERT OR IGNORE INTO speaker_aliases (speaker_id, alias) VALUES (?, ?)",
                (speaker_id, alias),
            )
        return int(speaker_id)

    def list_terms(
        self,
        *,
        type_: str | None = None,
        domain: str | None = None,
        status: str | None = None,
        search: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        """List terms with their aliases, filterable by type/domain/status/search."""
        clauses: list[str] = []
        params: list[object] = []
        if type_:
            clauses.append("t.type = ?")
            params.append(type_)
        if domain:
            clauses.append("(t.domain = ? OR t.domain IS NULL)")
            params.append(domain)
        if status:
            clauses.append("t.status = ?")
            params.append(status)
        if search:
            clauses.append(
                "(t.canonical LIKE ? OR EXISTS (SELECT 1 FROM term_aliases a WHERE a.term_id = t.id AND a.alias LIKE ?))"
            )
            like = f"%{search}%"
            params.extend([like, like])

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)

        rows = self._conn.execute(
            f"""
            SELECT t.id, t.canonical, t.type, t.domain, t.status, t.confidence,
                   t.confirm_count, t.reject_count, t.times_used,
                   t.created_at, t.updated_at, t.last_used_at, t.definition, t.notes
            FROM terms t
            {where}
            ORDER BY t.last_used_at DESC NULLS LAST, t.updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()

        results = []
        for r in rows:
            aliases = [
                a["alias"]
                for a in self._conn.execute(
                    "SELECT alias FROM term_aliases WHERE term_id = ? ORDER BY seen_count DESC",
                    (r["id"],),
                ).fetchall()
            ]
            results.append(
                {
                    "id": r["id"],
                    "canonical": r["canonical"],
                    "type": r["type"],
                    "domain": r["domain"],
                    "status": r["status"],
                    "confidence": r["confidence"],
                    "confirm_count": r["confirm_count"],
                    "reject_count": r["reject_count"],
                    "times_used": r["times_used"],
                    "definition": r["definition"],
                    "notes": r["notes"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "last_used_at": r["last_used_at"],
                    "aliases": aliases,
                }
            )
        return results

    def update_term(
        self,
        term_id: int,
        *,
        canonical: str | None = None,
        type_: str | None = None,
        domain: str | None = None,
        status: str | None = None,
        definition: str | None = None,
        notes: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        """Update fields on a term. Pass aliases to replace the alias set."""
        sets: list[str] = []
        params: list[object] = []
        for field, value in [
            ("canonical", canonical),
            ("type", type_),
            ("domain", domain),
            ("status", status),
            ("definition", definition),
            ("notes", notes),
        ]:
            if value is not None:
                sets.append(f"{field} = ?")
                params.append(value)

        if sets:
            sets.append("updated_at = CURRENT_TIMESTAMP")
            params.append(term_id)
            self._conn.execute(f"UPDATE terms SET {', '.join(sets)} WHERE id = ?", tuple(params))

        if aliases is not None:
            self._conn.execute("DELETE FROM term_aliases WHERE term_id = ?", (term_id,))
            for alias in aliases:
                self._conn.execute(
                    "INSERT OR IGNORE INTO term_aliases (term_id, alias, alias_type) VALUES (?, ?, ?)",
                    (term_id, alias, "asr-error"),
                )

    def delete_term(self, term_id: int) -> None:
        self._conn.execute("DELETE FROM terms WHERE id = ?", (term_id,))

    def list_speakers(self, *, search: str | None = None, limit: int = 500) -> list[dict]:
        clauses: list[str] = []
        params: list[object] = []
        if search:
            clauses.append(
                "(s.canonical_name LIKE ? OR EXISTS (SELECT 1 FROM speaker_aliases a WHERE a.speaker_id = s.id AND a.alias LIKE ?))"
            )
            like = f"%{search}%"
            params.extend([like, like])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)

        rows = self._conn.execute(
            f"""
            SELECT s.id, s.canonical_name, s.display_label, s.primary_language,
                   s.times_seen, s.confidence, s.notes, s.created_at
            FROM speakers s
            {where}
            ORDER BY s.times_seen DESC, s.created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()

        results = []
        for r in rows:
            aliases = [
                a["alias"]
                for a in self._conn.execute(
                    "SELECT alias FROM speaker_aliases WHERE speaker_id = ?", (r["id"],)
                ).fetchall()
            ]
            results.append(
                {
                    "id": r["id"],
                    "canonical_name": r["canonical_name"],
                    "display_label": r["display_label"],
                    "primary_language": r["primary_language"],
                    "times_seen": r["times_seen"],
                    "confidence": r["confidence"],
                    "notes": r["notes"],
                    "created_at": r["created_at"],
                    "aliases": aliases,
                }
            )
        return results

    def update_speaker(
        self,
        speaker_id: int,
        *,
        canonical_name: str | None = None,
        display_label: str | None = None,
        primary_language: str | None = None,
        notes: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        sets: list[str] = []
        params: list[object] = []
        for field, value in [
            ("canonical_name", canonical_name),
            ("display_label", display_label),
            ("primary_language", primary_language),
            ("notes", notes),
        ]:
            if value is not None:
                sets.append(f"{field} = ?")
                params.append(value)
        if sets:
            params.append(speaker_id)
            self._conn.execute(f"UPDATE speakers SET {', '.join(sets)} WHERE id = ?", tuple(params))
        if aliases is not None:
            self._conn.execute("DELETE FROM speaker_aliases WHERE speaker_id = ?", (speaker_id,))
            for alias in aliases:
                self._conn.execute(
                    "INSERT OR IGNORE INTO speaker_aliases (speaker_id, alias) VALUES (?, ?)",
                    (speaker_id, alias),
                )

    def delete_speaker(self, speaker_id: int) -> None:
        self._conn.execute("DELETE FROM speakers WHERE id = ?", (speaker_id,))

    def lookup_speaker(self, alias: str) -> SpeakerHit | None:
        row = self._conn.execute(
            """
            SELECT s.canonical_name, s.display_label, sa.alias
            FROM speaker_aliases sa
            JOIN speakers s ON s.id = sa.speaker_id
            WHERE sa.alias = ?
            LIMIT 1
            """,
            (alias,),
        ).fetchone()
        if not row:
            return None
        return SpeakerHit(
            canonical_name=row["canonical_name"],
            display_label=row["display_label"],
            matched_alias=row["alias"],
        )

    # --- Sessions ---

    def start_session(
        self,
        project_slug: str,
        provider: str,
        model: str,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO sessions (project_slug, provider, model) VALUES (?, ?, ?)",
            (project_slug, provider, model),
        )
        return int(cur.lastrowid or 0)

    def finish_session(
        self,
        session_id: int,
        *,
        input_tokens: int,
        output_tokens: int,
        status: str = "complete",
    ) -> None:
        self._conn.execute(
            """
            UPDATE sessions
            SET ended_at = CURRENT_TIMESTAMP,
                input_tokens = ?,
                output_tokens = ?,
                status = ?
            WHERE id = ?
            """,
            (input_tokens, output_tokens, status, session_id),
        )

    def list_edit_patterns(self, *, domain: str | None = None) -> list[dict]:
        clauses: list[str] = []
        params: list[object] = []
        if domain:
            clauses.append("(domain = ? OR domain IS NULL)")
            params.append(domain)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._conn.execute(
            f"""
            SELECT id, title, trigger_desc, action, rationale, domain,
                   confirmed_count, last_applied_at, created_at
            FROM edit_patterns
            {where}
            ORDER BY confirmed_count DESC, created_at DESC
            """,
            tuple(params),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_edit_pattern(
        self,
        *,
        title: str,
        trigger_desc: str,
        action: str,
        rationale: str | None = None,
        domain: str | None = None,
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO edit_patterns (title, trigger_desc, action, rationale, domain)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, trigger_desc, action, rationale, domain),
        )
        return int(cur.lastrowid or 0)

    def delete_edit_pattern(self, pattern_id: int) -> None:
        self._conn.execute("DELETE FROM edit_patterns WHERE id = ?", (pattern_id,))

    def add_negative(
        self,
        *,
        text: str,
        do_not_change_to: str | None = None,
        domain: str | None = None,
        reason: str | None = None,
    ) -> None:
        # SQLite treats NULL values as distinct in UNIQUE constraints, so we
        # have to do an explicit existence check to dedupe negatives that share
        # the same text/target/domain but were inserted with different reasons.
        existing = self._conn.execute(
            """
            SELECT id FROM negative_corrections
            WHERE text = ?
              AND COALESCE(do_not_change_to, '') = COALESCE(?, '')
              AND COALESCE(domain, '') = COALESCE(?, '')
            LIMIT 1
            """,
            (text, do_not_change_to, domain),
        ).fetchone()
        if existing:
            return
        self._conn.execute(
            """
            INSERT INTO negative_corrections (text, do_not_change_to, domain, reason)
            VALUES (?, ?, ?, ?)
            """,
            (text, do_not_change_to, domain, reason),
        )

    def list_negatives(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, text, do_not_change_to, domain, reason, created_at FROM negative_corrections ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, int]:
        terms = self._conn.execute("SELECT COUNT(*) FROM terms").fetchone()[0]
        verified = self._conn.execute(
            "SELECT COUNT(*) FROM terms WHERE status = 'verified'"
        ).fetchone()[0]
        confirmed = self._conn.execute(
            "SELECT COUNT(*) FROM terms WHERE status = 'confirmed'"
        ).fetchone()[0]
        proposed = self._conn.execute(
            "SELECT COUNT(*) FROM terms WHERE status = 'proposed'"
        ).fetchone()[0]
        speakers = self._conn.execute("SELECT COUNT(*) FROM speakers").fetchone()[0]
        patterns = self._conn.execute("SELECT COUNT(*) FROM edit_patterns").fetchone()[0]
        negatives = self._conn.execute("SELECT COUNT(*) FROM negative_corrections").fetchone()[0]
        sessions = self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        return {
            "terms": terms,
            "verified_terms": verified,
            "confirmed_terms": confirmed,
            "proposed_terms": proposed,
            "speakers": speakers,
            "edit_patterns": patterns,
            "negative_rules": negatives,
            "sessions": sessions,
        }

    # --- Export / Import ---

    def export_dict(self) -> dict:
        """Serialize the full library to a plain dict (suitable for JSON).

        The shape is versioned (``schema_version``) so future imports can
        migrate from older exports. Includes terms (with aliases), speakers
        (with aliases), edit patterns, and negative rules. ``sessions`` and
        ``applied_corrections`` are tracking data, not portable knowledge,
        so they're excluded by design.
        """
        term_rows = self._conn.execute(
            "SELECT id, canonical, type, domain, status, confidence, definition, notes "
            "FROM terms WHERE status != 'deprecated'"
        ).fetchall()
        terms: list[dict] = []
        for r in term_rows:
            aliases = [
                row["alias"]
                for row in self._conn.execute(
                    "SELECT alias FROM term_aliases WHERE term_id = ?", (r["id"],)
                ).fetchall()
            ]
            terms.append(
                {
                    "canonical": r["canonical"],
                    "type": r["type"],
                    "domain": r["domain"],
                    "status": r["status"],
                    "confidence": r["confidence"],
                    "definition": r["definition"],
                    "notes": r["notes"],
                    "aliases": aliases,
                }
            )

        speaker_rows = self._conn.execute(
            "SELECT id, canonical_name, display_label, primary_language, notes FROM speakers"
        ).fetchall()
        speakers: list[dict] = []
        for r in speaker_rows:
            aliases = [
                row["alias"]
                for row in self._conn.execute(
                    "SELECT alias FROM speaker_aliases WHERE speaker_id = ?", (r["id"],)
                ).fetchall()
            ]
            speakers.append(
                {
                    "canonical_name": r["canonical_name"],
                    "display_label": r["display_label"],
                    "primary_language": r["primary_language"],
                    "notes": r["notes"],
                    "aliases": aliases,
                }
            )

        patterns = [
            dict(row)
            for row in self._conn.execute(
                "SELECT title, trigger_desc, action, rationale, domain FROM edit_patterns"
            ).fetchall()
        ]

        negatives = [
            dict(row)
            for row in self._conn.execute(
                "SELECT text, do_not_change_to, domain, reason FROM negative_corrections"
            ).fetchall()
        ]

        return {
            "schema_version": 1,
            "format": "clearscript-library-export",
            "terms": terms,
            "speakers": speakers,
            "edit_patterns": patterns,
            "negatives": negatives,
        }

    def import_dict(self, payload: dict) -> dict:
        """Merge a library export into this library.

        Strategy: union of records — terms with a matching canonical have
        their aliases extended; speakers with a matching canonical_name
        get their aliases extended; patterns and negatives are inserted
        verbatim (relying on UNIQUE constraints to dedupe).

        Returns a summary: ``{terms_added, terms_merged, speakers_added,
        speakers_merged, patterns_added, negatives_added, skipped}``.
        """
        if not isinstance(payload, dict):
            raise ValueError("import payload must be a dict")
        if payload.get("format") != "clearscript-library-export":
            raise ValueError(
                "import payload missing 'format: clearscript-library-export' marker"
            )

        result = {
            "terms_added": 0,
            "terms_merged": 0,
            "speakers_added": 0,
            "speakers_merged": 0,
            "patterns_added": 0,
            "negatives_added": 0,
            "skipped": 0,
        }

        for t in payload.get("terms", []):
            canonical = (t.get("canonical") or "").strip()
            if not canonical:
                result["skipped"] += 1
                continue
            existing = self._conn.execute(
                "SELECT id FROM terms WHERE canonical = ?", (canonical,)
            ).fetchone()
            self.add_term(
                canonical=canonical,
                type_=t.get("type"),
                domain=t.get("domain"),
                aliases=t.get("aliases", []) or [],
            )
            if existing:
                result["terms_merged"] += 1
            else:
                result["terms_added"] += 1

        for s in payload.get("speakers", []):
            cn = (s.get("canonical_name") or "").strip()
            dl = (s.get("display_label") or "").strip()
            if not cn or not dl:
                result["skipped"] += 1
                continue
            existing = self._conn.execute(
                "SELECT id FROM speakers WHERE canonical_name = ?", (cn,)
            ).fetchone()
            self.add_speaker(
                canonical_name=cn,
                display_label=dl,
                aliases=s.get("aliases", []) or [],
                primary_language=s.get("primary_language"),
            )
            if existing:
                result["speakers_merged"] += 1
            else:
                result["speakers_added"] += 1

        for p in payload.get("edit_patterns", []):
            title = (p.get("title") or "").strip()
            trigger = (p.get("trigger_desc") or "").strip()
            action = (p.get("action") or "").strip()
            if not (title and trigger and action):
                result["skipped"] += 1
                continue
            self.add_edit_pattern(
                title=title,
                trigger_desc=trigger,
                action=action,
                rationale=p.get("rationale"),
                domain=p.get("domain"),
            )
            result["patterns_added"] += 1

        for n in payload.get("negatives", []):
            text = (n.get("text") or "").strip()
            if not text:
                result["skipped"] += 1
                continue
            self.add_negative(
                text=text,
                do_not_change_to=n.get("do_not_change_to"),
                domain=n.get("domain"),
                reason=n.get("reason"),
            )
            result["negatives_added"] += 1

        return result

    def bulk_delete_terms(self, term_ids: list[int]) -> int:
        """Delete multiple terms by id; returns the number actually deleted.

        Aliases cascade via ON DELETE CASCADE in the schema.
        """
        if not term_ids:
            return 0
        # First find which IDs actually exist so we can return a truthful count.
        check_placeholders = ",".join("?" * len(term_ids))
        present = self._conn.execute(
            f"SELECT id FROM terms WHERE id IN ({check_placeholders})", term_ids
        ).fetchall()
        ids_present = [r["id"] for r in present]
        if not ids_present:
            return 0
        # Now rebuild placeholders for the *actual* deletion set.
        delete_placeholders = ",".join("?" * len(ids_present))
        self._conn.execute(
            f"DELETE FROM terms WHERE id IN ({delete_placeholders})", ids_present
        )
        return len(ids_present)

    def close(self) -> None:
        self._conn.close()
