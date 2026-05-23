"""End-to-end HTTP tests for the FastAPI server.

These tests exercise the full request → response flow with a TestClient,
mocking out only the LLM provider so we don't make real network calls.
Config and storage paths are redirected to a per-test tmp dir so we
don't touch the user's real ~/Documents/clearscript/.

Covers:
- Health, providers, supported-formats, example, cost preview
- /api/run (sync) + /api/run-stream (SSE)
- /api/run-file (multipart upload)
- /api/projects CRUD: list, get, delete, transcript md
- /api/projects/{slug}/rerun (the v0.0.11 feature)
- /api/library CRUD: stats, terms (list/add/update/delete), speakers,
  patterns, negatives, suggestions accept
- /api/export/docx
- /api/estimate-cost
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clearscript.providers.base import ChatMessage, ChatResponse


class StubProvider:
    """A provider that returns a canned three-section response.

    Captures all calls so tests can assert what was sent.
    """

    name = "stub"

    def __init__(self, response_text: str | None = None) -> None:
        self.response_text = response_text or (
            "Speaker A: Cleaned text here.\n"
            "---CHANGELOG---\n"
            '[{"layer": "L3", "before": "Tabby", "after": "Tavily", "reason": "company"}]\n'
            "---SUGGESTIONS---\n"
            '[{"kind": "term", "canonical": "Tavily", "aliases": ["Tabby"]}]'
        )
        self.calls: list[list[ChatMessage]] = []

    def chat(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(list(messages))
        return ChatResponse(
            text=self.response_text,
            input_tokens=120,
            output_tokens=80,
            model=model,
            provider=self.name,
            latency_ms=1.0,
        )

    def stream(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        yield self.response_text

    def chat_with_progress(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(list(messages))
        # Two delta events so we can verify the SSE stream emits multiple.
        mid = len(self.response_text) // 2
        yield ("delta", self.response_text[:mid])
        yield ("delta", self.response_text[mid:])
        yield (
            "done",
            ChatResponse(
                text=self.response_text,
                input_tokens=120,
                output_tokens=80,
                model=model,
                provider=self.name,
                latency_ms=1.0,
            ),
        )


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Build a TestClient with config/storage redirected to a tmp dir.

    The provider factory is patched so requests don't hit a real LLM.
    Returns ``(client, stub_provider)`` so tests can inspect what got sent.
    """
    # Redirect XDG-ish dirs so tests don't touch the user's real install.
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

    stub = StubProvider()
    monkeypatch.setattr("clearscript.server.build_provider", lambda _cfg: stub)

    # create_app must be imported AFTER monkeypatch is applied so the
    # patched build_provider is captured in the closure.
    from clearscript.server import create_app

    app = create_app()
    client = TestClient(app)
    return client, stub


# ============ Smoke / discovery endpoints ============


def test_health(app_client) -> None:
    client, _ = app_client
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_providers_lists_builtins(app_client) -> None:
    client, _ = app_client
    res = client.get("/api/providers")
    assert res.status_code == 200
    body = res.json()
    names = [p["name"] for p in body["providers"]]
    # The five built-in adapters should always be listed.
    for expected in ("claude", "openai", "deepseek", "gemini", "ollama"):
        assert expected in names, f"missing builtin provider: {expected}"


def test_supported_formats_lists_all_text_formats(app_client) -> None:
    client, _ = app_client
    res = client.get("/api/supported-formats")
    assert res.status_code == 200
    exts = res.json()["extensions"]
    assert ".txt" in exts
    assert ".srt" in exts
    assert ".vtt" in exts
    assert ".json" in exts
    assert ".md" in exts


def test_example_endpoint_returns_a_transcript(app_client) -> None:
    client, _ = app_client
    res = client.get("/api/example")
    assert res.status_code == 200
    body = res.json()
    assert "transcript" in body
    assert len(body["transcript"]) > 100  # not just placeholder


def test_serve_index_returns_html(app_client) -> None:
    client, _ = app_client
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    # The Bauhaus title chunk should always be present in the SPA shell.
    assert "clearscript" in res.text.lower()


# ============ /api/run (sync) ============


def test_run_happy_path(app_client) -> None:
    client, stub = app_client
    res = client.post(
        "/api/run",
        json={
            "transcript": "Speaker 1: Hello there.\nSpeaker 2: Hi.",
            "format": "txt",
            "title": "Test run",
            "briefing": "",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["edited_markdown"]
    assert body["model"]
    assert body["provider"] == "stub"
    assert body["project_slug"]  # saved to disk
    assert body["input_tokens"] == 120
    assert body["output_tokens"] == 80
    # The provider was actually invoked.
    assert len(stub.calls) >= 1


def test_run_rejects_empty_transcript(app_client) -> None:
    client, _ = app_client
    res = client.post("/api/run", json={"transcript": "   \n\n"})
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()


def test_run_rejects_bad_format(app_client) -> None:
    client, _ = app_client
    # JSON adapter on plain text raises ValueError → 400
    res = client.post(
        "/api/run",
        json={"transcript": "not json at all", "format": "json"},
    )
    assert res.status_code == 400


def test_run_unknown_provider_returns_400(app_client) -> None:
    client, _ = app_client
    res = client.post(
        "/api/run",
        json={"transcript": "Speaker 1: hi.", "provider": "doesnotexist"},
    )
    assert res.status_code == 400


# ============ /api/run-stream (SSE) ============


def test_run_stream_emits_expected_events(app_client) -> None:
    """SSE stream must yield plan → chunk_start → chunk_delta+ → chunk_done → complete → saved."""
    client, _ = app_client
    with client.stream(
        "POST",
        "/api/run-stream",
        json={"transcript": "Speaker 1: Hi.\nSpeaker 2: Hello.", "format": "txt"},
    ) as res:
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        body = "".join(res.iter_text())

    # Parse event names out of the SSE body.
    event_names = [
        line.split("event: ", 1)[1].strip()
        for line in body.splitlines()
        if line.startswith("event: ")
    ]
    assert "plan" in event_names
    assert "chunk_start" in event_names
    assert "chunk_delta" in event_names
    assert "chunk_done" in event_names
    assert "complete" in event_names
    assert "saved" in event_names
    # plan must come first, saved last.
    assert event_names[0] == "plan"
    assert event_names[-1] == "saved"


def test_run_stream_rejects_empty(app_client) -> None:
    client, _ = app_client
    res = client.post("/api/run-stream", json={"transcript": ""})
    assert res.status_code == 400


# ============ /api/run-file (multipart upload) ============


def test_run_file_with_txt_upload(app_client) -> None:
    client, _ = app_client
    files = {"file": ("test.txt", b"Speaker 1: hello world\n", "text/plain")}
    res = client.post("/api/run-file", files=files, data={"title": "Upload"})
    assert res.status_code == 200
    body = res.json()
    assert body["edited_markdown"]
    assert body["project_slug"]


def test_run_file_rejects_unsupported_extension(app_client) -> None:
    client, _ = app_client
    files = {"file": ("test.xyz", b"random bytes", "application/octet-stream")}
    res = client.post("/api/run-file", files=files)
    assert res.status_code == 400


# ============ /api/projects ============


def test_projects_lifecycle_list_get_delete(app_client) -> None:
    client, _ = app_client
    # Create a project via /api/run.
    res = client.post(
        "/api/run",
        json={"transcript": "Speaker 1: project test.\n", "title": "Lifecycle"},
    )
    slug = res.json()["project_slug"]

    # List should include it.
    res = client.get("/api/projects")
    assert res.status_code == 200
    projects = res.json()["projects"]
    assert any(p["slug"] == slug for p in projects)

    # Detail should round-trip.
    res = client.get(f"/api/projects/{slug}")
    assert res.status_code == 200
    detail = res.json()
    assert detail["slug"] == slug
    assert detail["title"] == "Lifecycle"
    assert "cleaned_markdown" in detail

    # Markdown download.
    res = client.get(f"/api/projects/{slug}/transcript.md")
    assert res.status_code == 200
    assert b"Cleaned text" in res.content

    # Delete.
    res = client.delete(f"/api/projects/{slug}")
    assert res.status_code == 204
    res = client.get(f"/api/projects/{slug}")
    assert res.status_code == 404


def test_project_transcript_patch_updates_cleaned_md(app_client) -> None:
    client, _ = app_client
    slug = client.post(
        "/api/run", json={"transcript": "Speaker 1: edit me.\n"}
    ).json()["project_slug"]

    res = client.patch(
        f"/api/projects/{slug}/transcript",
        json={"cleaned_markdown": "Manually edited content."},
    )
    assert res.status_code == 200

    res = client.get(f"/api/projects/{slug}")
    assert res.json()["cleaned_markdown"].strip() == "Manually edited content."


def test_project_404_for_unknown_slug(app_client) -> None:
    client, _ = app_client
    res = client.get("/api/projects/this-slug-does-not-exist")
    assert res.status_code == 404


# ============ /api/projects/{slug}/rerun (v0.0.11) ============


def test_project_rerun_creates_sibling(app_client) -> None:
    """Re-running a project produces a NEW project with rerun_of set."""
    client, _stub = app_client
    # Original run.
    orig_slug = client.post(
        "/api/run",
        json={
            "transcript": "Speaker 1: Original content with Tabby.\n",
            "title": "Original",
        },
    ).json()["project_slug"]

    # Re-run via SSE.
    with client.stream(
        "POST",
        f"/api/projects/{orig_slug}/rerun",
        json={},
    ) as res:
        body = "".join(res.iter_text())
        assert res.status_code == 200, f"rerun status {res.status_code}: {body}"

    # The saved event payload carries the new slug.
    saved_lines = [
        line for line in body.splitlines() if line.startswith("data: ")
    ]
    assert saved_lines, "no SSE data lines came back"
    # Parse the last data line (paired with saved event).
    # Easier: just verify a new project appeared in the list.
    projects = client.get("/api/projects").json()["projects"]
    slugs = [p["slug"] for p in projects]
    rerun_slugs = [s for s in slugs if s.endswith("-rerun")]
    assert rerun_slugs, "expected a -rerun sibling project"
    assert orig_slug in slugs, "original must be preserved"

    # The new project's meta should carry rerun_of pointer.
    rerun_slug = rerun_slugs[0]
    detail = client.get(f"/api/projects/{rerun_slug}").json()
    assert detail.get("rerun_of") == orig_slug


def test_project_rerun_404_for_missing_slug(app_client) -> None:
    client, _ = app_client
    res = client.post("/api/projects/no-such-slug/rerun", json={})
    assert res.status_code == 404


# ============ /api/library CRUD ============


def test_library_stats(app_client) -> None:
    client, _ = app_client
    res = client.get("/api/library/stats")
    assert res.status_code == 200
    stats = res.json()
    # Seed pack auto-installs on first library open, so terms should be > 0.
    assert stats["terms"] >= 15
    assert stats["negative_rules"] >= 3


def test_library_terms_crud(app_client) -> None:
    client, _ = app_client

    # Add a term.
    res = client.post(
        "/api/library/terms",
        json={
            "canonical": "TestCorp",
            "type": "company",
            "domain": "test",
            "aliases": ["TestCo", "Test Corp"],
        },
    )
    assert res.status_code == 201
    new_term = res.json()
    term_id = new_term["id"]

    # List includes the new term.
    res = client.get("/api/library/terms?q=TestCorp")
    assert res.status_code == 200
    terms = res.json()["terms"]
    assert any(t["id"] == term_id for t in terms)

    # Update.
    res = client.patch(
        f"/api/library/terms/{term_id}",
        json={"canonical": "TestCorp", "domain": "updated", "aliases": ["TestCo"]},
    )
    assert res.status_code == 200

    # Delete.
    res = client.delete(f"/api/library/terms/{term_id}")
    assert res.status_code == 204
    # Confirm gone.
    res = client.get("/api/library/terms?q=TestCorp")
    assert all(t["id"] != term_id for t in res.json()["terms"])


def test_library_term_lookup_finds_seed_pack_aliases(app_client) -> None:
    """Smoke test: seed pack got installed and is reachable via the lookup endpoint."""
    client, _ = app_client
    # Search for an alias of a seeded term.
    res = client.get("/api/library/terms?q=Tabby")
    assert res.status_code == 200
    terms = res.json()["terms"]
    # 'Tabby' is a seeded alias for 'Tavily'.
    canonicals = {t["canonical"] for t in terms}
    assert "Tavily" in canonicals or any(
        "Tabby" in (t.get("aliases") or []) for t in terms
    )


# ============ /api/estimate-cost ============


def test_estimate_cost_returns_breakdown(app_client) -> None:
    client, _ = app_client
    res = client.post(
        "/api/estimate-cost",
        json={"transcript": "Speaker 1: hi.\n" * 200, "provider": "claude"},
    )
    assert res.status_code == 200
    body = res.json()
    # CostEstimate.as_dict() shape — see clearscript.core.cost.CostEstimate.
    for key in (
        "input_tokens",
        "output_tokens_estimate",
        "input_cost_usd",
        "output_cost_usd",
        "total_cost_usd",
        "pricing_known",
    ):
        assert key in body, f"missing key {key} in cost response"
    assert body["input_tokens"] > 0
    assert body["total_cost_usd"] >= 0


# ============ /api/export/docx ============


def test_library_speakers_crud(app_client) -> None:
    client, _ = app_client
    # Add a speaker.
    res = client.post(
        "/api/library/speakers",
        json={
            "canonical_name": "Siqi Chen",
            "display_label": "Siqi：",
            "primary_language": "zh",
            "aliases": ["Speaker 1", "host"],
        },
    )
    assert res.status_code == 201
    sid = res.json()["id"]

    # List.
    res = client.get("/api/library/speakers")
    assert res.status_code == 200
    speakers = res.json()["speakers"]
    assert any(s["id"] == sid for s in speakers)

    # Update.
    res = client.patch(
        f"/api/library/speakers/{sid}",
        json={
            "canonical_name": "Siqi Chen",
            "display_label": "Siqi (host)：",
            "primary_language": "zh",
            "aliases": [],
        },
    )
    assert res.status_code == 200

    # Delete.
    res = client.delete(f"/api/library/speakers/{sid}")
    assert res.status_code == 204


def test_library_patterns_crud(app_client) -> None:
    client, _ = app_client
    res = client.post(
        "/api/library/patterns",
        json={
            "title": "Drop redundant openers",
            "trigger_desc": "Sentences starting with '其实就是'",
            "action": "Strip the opener, keep the substantive content",
            "rationale": "L2 trim — speaker fillers are noise",
            "domain": "vc",
        },
    )
    assert res.status_code == 201
    pid = res.json()["id"]

    res = client.get("/api/library/patterns")
    assert res.status_code == 200
    assert any(p["id"] == pid for p in res.json()["patterns"])

    res = client.delete(f"/api/library/patterns/{pid}")
    assert res.status_code == 204


def test_library_accept_suggestions_landed_in_db(app_client) -> None:
    """Mode B harvest: posting LLM suggestions into the library."""
    client, _ = app_client
    res = client.post(
        "/api/library/accept-suggestions",
        json={
            "suggestions": [
                {
                    "kind": "term",
                    "canonical": "NewCorp",
                    "aliases_seen": ["new-corp", "NewCorpInc"],
                    "type": "company",
                    "domain": "test",
                },
                {
                    "kind": "speaker",
                    "canonical_name": "Jane Doe",
                    "display_label": "Jane：",
                    "aliases_seen": ["Speaker 2"],
                },
                {
                    "kind": "edit_pattern",
                    "title": "Trim filler 你知道",
                    "trigger_desc": "你知道 mid-sentence",
                    "action": "remove",
                    "rationale": "filler",
                },
                # Skipped: missing required fields.
                {"kind": "term"},
            ]
        },
    )
    assert res.status_code == 200
    accepted = res.json()["accepted"]
    assert accepted["terms"] == 1
    assert accepted["speakers"] == 1
    assert accepted["patterns"] == 1
    assert accepted["skipped"] == 1

    # Verify the term ended up searchable.
    res = client.get("/api/library/terms?q=NewCorp")
    assert any(t["canonical"] == "NewCorp" for t in res.json()["terms"])


def test_project_download_input_returns_binary(app_client) -> None:
    """The /input endpoint must return the raw file as-is (binary-safe)."""
    client, _ = app_client
    slug = client.post(
        "/api/run", json={"transcript": "raw bytes here"}
    ).json()["project_slug"]
    res = client.get(f"/api/projects/{slug}/input")
    assert res.status_code == 200
    assert b"raw bytes here" in res.content


def test_rerun_with_explicit_provider_override(app_client) -> None:
    """Caller can override provider/model in the rerun body."""
    client, _ = app_client
    orig_slug = client.post(
        "/api/run", json={"transcript": "Speaker 1: original.\n"}
    ).json()["project_slug"]
    # Explicitly request claude — stub stays bound to build_provider.
    with client.stream(
        "POST",
        f"/api/projects/{orig_slug}/rerun",
        json={"provider": "claude", "model": "claude-opus-4-7"},
    ) as res:
        body = "".join(res.iter_text())
        assert res.status_code == 200, f"got {res.status_code}: {body}"
    # The 'saved' event must reference a real new slug.
    assert "event: saved" in body
    assert "project_slug" in body


def test_library_export_returns_download(app_client) -> None:
    """The /api/library/export endpoint must return a JSON download with
    the right Content-Disposition so browsers prompt 'Save As'.
    """
    client, _ = app_client
    # Add a term first so the export has something to serialize.
    client.post(
        "/api/library/terms",
        json={"canonical": "Tavily", "aliases": ["Tabby"], "type": "company"},
    )
    res = client.get("/api/library/export")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    assert "clearscript-library.json" in res.headers.get(
        "content-disposition", ""
    )
    body = res.json()
    assert body["format"] == "clearscript-library-export"
    canonicals = {t["canonical"] for t in body["terms"]}
    assert "Tavily" in canonicals


def test_library_export_then_import_into_self_is_idempotent(app_client) -> None:
    """Exporting and re-importing the same payload must merge cleanly,
    not duplicate. The library's UNIQUE constraints handle it.
    """
    client, _ = app_client
    client.post(
        "/api/library/terms",
        json={"canonical": "Manus", "aliases": ["Minus"], "type": "company"},
    )
    export = client.get("/api/library/export").json()
    before = client.get("/api/library/stats").json()["terms"]

    res = client.post("/api/library/import", json=export)
    assert res.status_code == 200
    assert "summary" in res.json()

    after = client.get("/api/library/stats").json()["terms"]
    assert after == before  # idempotent — no duplicate rows


def test_library_import_rejects_garbage_payload(app_client) -> None:
    client, _ = app_client
    res = client.post(
        "/api/library/import",
        json={"random": "shape", "without": "format marker"},
    )
    assert res.status_code == 400


def test_library_bulk_delete_endpoint(app_client) -> None:
    client, _ = app_client
    # Create three terms.
    ids = []
    for canonical in ("Alpha", "Beta", "Gamma"):
        res = client.post(
            "/api/library/terms",
            json={"canonical": canonical, "aliases": []},
        )
        ids.append(res.json()["id"])

    res = client.post(
        "/api/library/terms/bulk-delete",
        json={"ids": ids[:2]},  # delete Alpha + Beta
    )
    assert res.status_code == 200
    assert res.json()["deleted"] == 2

    # Gamma still there.
    listing = client.get("/api/library/terms").json()["terms"]
    canonicals = {t["canonical"] for t in listing}
    assert "Gamma" in canonicals
    assert "Alpha" not in canonicals
    assert "Beta" not in canonicals


def test_library_bulk_delete_rejects_non_int_ids(app_client) -> None:
    client, _ = app_client
    res = client.post(
        "/api/library/terms/bulk-delete",
        json={"ids": ["not-an-int", 5]},
    )
    assert res.status_code == 400


def test_library_negatives_crud(app_client) -> None:
    """List → add → list (sees new) → delete → list (gone)."""
    client, _ = app_client

    # Initial state — seed pack ships 3 negatives.
    initial = client.get("/api/library/negatives").json()["negatives"]
    initial_count = len(initial)

    # Add a new one.
    res = client.post(
        "/api/library/negatives",
        json={
            "text": "其实就是",
            "do_not_change_to": "就是",
            "domain": "vc",
            "reason": "preserve speaker's filler",
        },
    )
    assert res.status_code == 201

    listing = client.get("/api/library/negatives").json()["negatives"]
    assert len(listing) == initial_count + 1
    new_rule = next(n for n in listing if n["text"] == "其实就是")
    assert new_rule["do_not_change_to"] == "就是"
    assert new_rule["domain"] == "vc"

    # Delete it.
    res = client.delete(f"/api/library/negatives/{new_rule['id']}")
    assert res.status_code == 204
    final = client.get("/api/library/negatives").json()["negatives"]
    assert len(final) == initial_count


def test_library_negative_add_rejects_empty_text(app_client) -> None:
    client, _ = app_client
    res = client.post(
        "/api/library/negatives",
        json={"text": "   "},  # whitespace only
    )
    assert res.status_code == 400


def test_library_negative_delete_404_for_missing_id(app_client) -> None:
    client, _ = app_client
    res = client.delete("/api/library/negatives/99999")
    assert res.status_code == 404


def test_project_compare_returns_diff(app_client) -> None:
    """GET /api/projects/{left}/compare?with=<right> returns both sides + diff."""
    client, stub = app_client

    # Make one project.
    slug_a = client.post(
        "/api/run", json={"transcript": "Speaker 1: First content.\n"}
    ).json()["project_slug"]

    # Change the stub's output so the second project's cleaned_md differs.
    stub.response_text = (
        "Speaker B: DIFFERENT cleaned text.\n"
        "---CHANGELOG---\n[]\n"
        "---SUGGESTIONS---\n[]"
    )
    slug_b = client.post(
        "/api/run", json={"transcript": "Speaker 1: Second content.\n"}
    ).json()["project_slug"]

    res = client.get(f"/api/projects/{slug_a}/compare?with={slug_b}")
    assert res.status_code == 200
    body = res.json()
    assert body["left"]["slug"] == slug_a
    assert body["right"]["slug"] == slug_b
    assert body["left"]["cleaned_markdown"]
    assert body["right"]["cleaned_markdown"]
    assert "unified_diff" in body
    assert "+" in body["unified_diff"] or "-" in body["unified_diff"]
    assert body["stats"]["identical"] is False
    assert body["stats"]["added"] + body["stats"]["removed"] > 0


def test_project_compare_identical_when_same_output(app_client) -> None:
    client, _ = app_client
    slug_a = client.post(
        "/api/run", json={"transcript": "Speaker 1: Same.\n"}
    ).json()["project_slug"]
    slug_b = client.post(
        "/api/run", json={"transcript": "Speaker 2: Same.\n"}
    ).json()["project_slug"]
    res = client.get(f"/api/projects/{slug_a}/compare?with={slug_b}")
    assert res.status_code == 200
    # Same stub response means cleaned_markdown is identical.
    assert res.json()["stats"]["identical"] is True


def test_project_compare_404_if_either_missing(app_client) -> None:
    client, _ = app_client
    slug = client.post(
        "/api/run", json={"transcript": "Speaker 1: hi.\n"}
    ).json()["project_slug"]

    res = client.get(f"/api/projects/{slug}/compare?with=no-such-slug")
    assert res.status_code == 404

    res = client.get(f"/api/projects/no-such-slug/compare?with={slug}")
    assert res.status_code == 404


def test_library_health_endpoint_returns_summary(app_client) -> None:
    """GET /api/library/health returns the shape expected by the UI."""
    client, _ = app_client
    # Force a duplicate alias so the report has content to verify.
    client.post(
        "/api/library/terms",
        json={"canonical": "Foo", "aliases": ["x"]},
    )
    client.post(
        "/api/library/terms",
        json={"canonical": "Bar", "aliases": ["x"]},  # same alias 'x'
    )
    res = client.get("/api/library/health")
    assert res.status_code == 200
    body = res.json()
    for key in (
        "duplicate_aliases",
        "low_confidence_terms",
        "stale_terms",
        "summary",
    ):
        assert key in body, f"missing key {key}"
    # The duplicate we created shows up.
    aliases_listed = [d["alias"] for d in body["duplicate_aliases"]]
    assert "x" in aliases_listed


def test_library_health_respects_stale_days_query(app_client) -> None:
    client, _ = app_client
    res = client.get("/api/library/health?stale_days=7")
    assert res.status_code == 200
    assert res.json()["stale_days_threshold"] == 7


def test_library_export_md_endpoint_returns_markdown(app_client) -> None:
    """GET /api/library/export.md serves a markdown download."""
    client, _ = app_client
    client.post(
        "/api/library/terms",
        json={"canonical": "MarkdownMe", "aliases": ["mm"], "type": "company"},
    )
    res = client.get("/api/library/export.md")
    assert res.status_code == 200
    assert "text/markdown" in res.headers["content-type"]
    assert ".md" in res.headers.get("content-disposition", "")
    body = res.text
    assert body.startswith("# clearscript library")
    assert "MarkdownMe" in body


def test_project_summary_carries_rerun_of_pointer(app_client) -> None:
    """A reran project must surface rerun_of in /api/projects so the UI
    can render the provenance badge.
    """
    client, _ = app_client
    orig = client.post(
        "/api/run", json={"transcript": "Speaker 1: original.\n"}
    ).json()["project_slug"]
    with client.stream(
        "POST", f"/api/projects/{orig}/rerun", json={}
    ) as res:
        "".join(res.iter_text())
        assert res.status_code == 200

    projects = client.get("/api/projects").json()["projects"]
    rerun_entries = [p for p in projects if p.get("rerun_of") == orig]
    assert rerun_entries, "rerun_of must be exposed in project list"


def test_export_docx_returns_binary(app_client) -> None:
    client, _ = app_client
    res = client.post(
        "/api/export/docx",
        json={
            "markdown": "# Title\n\nSpeaker A:\n- Hello.\n",
            "title": "Doc Title",
        },
    )
    assert res.status_code == 200
    assert "officedocument" in res.headers["content-type"]
    # .docx files are zip archives — first bytes are PK.
    assert res.content[:2] == b"PK"
