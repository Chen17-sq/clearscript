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
        # check_same_thread=False: the SSE endpoints hand sync generators to
        # Starlette, which drives each next() on a threadpool worker — calls
        # on the same Library instance can land on different threads. Access
        # is still sequential (one generator), so cross-thread use is safe;
        # without this flag SQLite raises ProgrammingError mid-stream.
        self._conn = sqlite3.connect(
            self.path, isolation_level=None, check_same_thread=False
        )
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
            try:
                cur = self._conn.execute(
                    """
                    INSERT INTO terms (canonical, type, domain, definition, scope)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (canonical, type_, domain, definition, scope),
                )
                term_id = cur.lastrowid
            except sqlite3.IntegrityError:
                # Check-then-insert race: a concurrent request inserted the
                # same canonical between our SELECT and INSERT. Re-fetch.
                row = self._conn.execute(
                    "SELECT id FROM terms WHERE canonical = ? AND scope = ?",
                    (canonical, scope),
                ).fetchone()
                if row is None:
                    raise
                term_id = row["id"]

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
        # FTS5 interprets bare input as query syntax — a user typing
        # `a AND`, `"unclosed`, or `term-` gets an OperationalError. Quote
        # each whitespace token as a phrase (doubling embedded quotes) so
        # arbitrary text is always a valid query, and fall back to a LIKE
        # scan if FTS still balks.
        tokens = [t.replace('"', '""') for t in query.split() if t]
        if not tokens:
            return []
        fts_query = " ".join(f'"{t}"' for t in tokens)
        try:
            rows = self._conn.execute(
                """
                SELECT t.canonical, '' AS alias, t.confidence, t.domain, t.type
                FROM terms_fts f
                JOIN terms t ON t.id = f.rowid
                WHERE terms_fts MATCH ?
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            like = f"%{query}%"
            rows = self._conn.execute(
                """
                SELECT canonical, '' AS alias, confidence, domain, type
                FROM terms
                WHERE canonical LIKE ?
                LIMIT ?
                """,
                (like, limit),
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
            # Parenthesize the OR: SQL AND binds tighter, so the unparenthesized
            # version returned every deprecated NULL-domain term.
            rows = self._conn.execute(
                "SELECT canonical, '' as alias, confidence, domain, type FROM terms "
                "WHERE (domain IS NULL OR domain = ?) AND status != 'deprecated'",
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

    def delete_negative(self, negative_id: int) -> bool:
        """Delete a negative-correction rule. Returns True if a row was removed."""
        cursor = self._conn.execute(
            "DELETE FROM negative_corrections WHERE id = ?", (negative_id,)
        )
        return cursor.rowcount > 0

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
        for key in ("terms", "speakers", "edit_patterns", "negatives"):
            if key in payload and not isinstance(payload[key], list):
                raise ValueError(f"import payload field {key!r} must be a list")

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
            if not isinstance(t, dict):
                result["skipped"] += 1
                continue
            canonical = (t.get("canonical") or "").strip()
            if not canonical:
                result["skipped"] += 1
                continue
            existing = self._conn.execute(
                "SELECT id FROM terms WHERE canonical = ?", (canonical,)
            ).fetchone()
            term_id = self.add_term(
                canonical=canonical,
                type_=t.get("type"),
                domain=t.get("domain"),
                aliases=t.get("aliases", []) or [],
                definition=t.get("definition"),
            )
            # Preserve the curation state the exporter recorded — without
            # this, confirmed/verified terms round-trip back to 'proposed'
            # and the receiving user loses all the confidence the source
            # library had built up.
            status = t.get("status")
            notes = t.get("notes")
            if (status and status != "proposed") or notes:
                self.update_term(
                    term_id,
                    status=status if status and status != "proposed" else None,
                    notes=notes,
                )
            confidence = t.get("confidence")
            if isinstance(confidence, (int, float)) and not existing:
                self._conn.execute(
                    "UPDATE terms SET confidence = ? WHERE id = ?",
                    (float(confidence), term_id),
                )
            if existing:
                result["terms_merged"] += 1
            else:
                result["terms_added"] += 1

        for s in payload.get("speakers", []):
            if not isinstance(s, dict):
                result["skipped"] += 1
                continue
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
            if not isinstance(p, dict):
                result["skipped"] += 1
                continue
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
            if not isinstance(n, dict):
                result["skipped"] += 1
                continue
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

    def health_check(self, *, stale_days: int = 90) -> dict:
        """Return a health snapshot of the library.

        Highlights things the user probably wants to clean up:

        - **duplicate_aliases**: same alias text mapping to multiple
          canonicals — the lookup result is non-deterministic, so this is
          a real correctness risk for the pipeline.
        - **duplicate_canonicals**: the same canonical name added more
          than once (e.g. via two suggestion accepts before refresh).
        - **low_confidence_terms**: confidence < 0.3, still active —
          probably noise from a single accidental Mode B accept.
        - **stale_terms**: not used in ``stale_days`` days — candidates
          for archival if the user is doing library cleanup.
        - **orphan_aliases**: alias rows whose term_id no longer exists.
          Shouldn't happen with FK CASCADE but worth surfacing if it does.
        """
        duplicate_aliases = [
            dict(row)
            for row in self._conn.execute(
                """
                SELECT alias, GROUP_CONCAT(t.canonical, ' | ') AS canonicals,
                       COUNT(*) AS n
                FROM term_aliases a
                JOIN terms t ON t.id = a.term_id
                WHERE t.status != 'deprecated'
                GROUP BY alias
                HAVING n > 1
                ORDER BY n DESC, alias
                """
            ).fetchall()
        ]

        duplicate_canonicals = [
            dict(row)
            for row in self._conn.execute(
                """
                SELECT canonical, COUNT(*) AS n
                FROM terms
                WHERE status != 'deprecated'
                GROUP BY canonical
                HAVING n > 1
                ORDER BY n DESC, canonical
                """
            ).fetchall()
        ]

        low_confidence_terms = [
            dict(row)
            for row in self._conn.execute(
                """
                SELECT id, canonical, type, domain, confidence
                FROM terms
                WHERE status != 'deprecated' AND confidence < 0.3
                ORDER BY confidence ASC, canonical
                LIMIT 200
                """
            ).fetchall()
        ]

        stale_terms = [
            dict(row)
            for row in self._conn.execute(
                """
                SELECT id, canonical, type, domain, last_used_at, times_used
                FROM terms
                WHERE status != 'deprecated'
                  AND (
                    last_used_at IS NULL
                    OR last_used_at < datetime('now', ?)
                  )
                ORDER BY (last_used_at IS NULL) DESC, last_used_at ASC, canonical
                LIMIT 200
                """,
                (f"-{int(stale_days)} days",),
            ).fetchall()
        ]

        orphan_aliases = self._conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM term_aliases a
            LEFT JOIN terms t ON t.id = a.term_id
            WHERE t.id IS NULL
            """
        ).fetchone()["n"]

        return {
            "stale_days_threshold": int(stale_days),
            "duplicate_aliases": duplicate_aliases,
            "duplicate_canonicals": duplicate_canonicals,
            "low_confidence_terms": low_confidence_terms,
            "stale_terms": stale_terms,
            "orphan_aliases": orphan_aliases,
            "summary": {
                "duplicate_alias_groups": len(duplicate_aliases),
                "duplicate_canonical_groups": len(duplicate_canonicals),
                "low_confidence_count": len(low_confidence_terms),
                "stale_count": len(stale_terms),
                "orphan_alias_count": orphan_aliases,
            },
        }

    def export_markdown(self) -> str:
        """Render the library as a human-readable markdown document.

        Used by ``GET /api/library/export.md`` and ``lib export --md``.
        Git-friendly: stable section ordering and one entry per line so
        diffs show only what actually changed.
        """
        payload = self.export_dict()
        lines: list[str] = ["# clearscript library", ""]
        lines.append(
            f"_Exported from clearscript (schema v{payload['schema_version']}). "
            "Edit by hand at your own risk — re-import via "
            "`clearscript lib import`._"
        )
        lines.append("")

        terms_by_domain: dict[str, list[dict]] = {}
        for t in payload["terms"]:
            domain = t.get("domain") or "_"
            terms_by_domain.setdefault(domain, []).append(t)

        lines.append("## Terms")
        lines.append("")
        for domain in sorted(terms_by_domain.keys()):
            lines.append(f"### Domain: `{domain}`")
            lines.append("")
            for t in sorted(terms_by_domain[domain], key=lambda x: x["canonical"].lower()):
                aliases = ", ".join(f"`{a}`" for a in t.get("aliases", []))
                type_part = f" ({t['type']})" if t.get("type") else ""
                line = f"- **{t['canonical']}**{type_part}"
                if aliases:
                    line += f" ← {aliases}"
                lines.append(line)
            lines.append("")

        if payload["speakers"]:
            lines.append("## Speakers")
            lines.append("")
            for s in sorted(
                payload["speakers"], key=lambda x: x["canonical_name"].lower()
            ):
                aliases = ", ".join(f"`{a}`" for a in s.get("aliases", []))
                lang = f" [{s['primary_language']}]" if s.get("primary_language") else ""
                line = f"- **{s['canonical_name']}** → `{s['display_label']}`{lang}"
                if aliases:
                    line += f" ← {aliases}"
                lines.append(line)
            lines.append("")

        if payload["edit_patterns"]:
            lines.append("## Edit patterns")
            lines.append("")
            for p in payload["edit_patterns"]:
                lines.append(f"- **{p['title']}**")
                lines.append(f"  - Trigger: {p['trigger_desc']}")
                lines.append(f"  - Action: {p['action']}")
                if p.get("rationale"):
                    lines.append(f"  - Rationale: {p['rationale']}")
            lines.append("")

        if payload["negatives"]:
            lines.append("## Negative rules (do-not-change)")
            lines.append("")
            for n in payload["negatives"]:
                target = (
                    f" (don't change to `{n['do_not_change_to']}`)"
                    if n.get("do_not_change_to")
                    else ""
                )
                line = f"- `{n['text']}`{target}"
                if n.get("reason"):
                    line += f" — {n['reason']}"
                lines.append(line)
            lines.append("")

        return "\n".join(lines)

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
