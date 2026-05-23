"""Integration test for the 'compounding library' claim in the README.

The promise: clearscript gets sharper with each transcript you run because
suggestions accumulate into a SQLite library that's injected into every
subsequent prompt. This test closes that loop end-to-end:

  Run 1: pipeline runs with empty library, model emits a suggestion (Tabby → Tavily)
  Accept: suggestion is persisted via accept-suggestions endpoint
  Run 2: pipeline runs again with a transcript that mentions 'Tabby';
         the system prompt now contains the library mapping
  Re-run: re-running the FIRST project against the now-populated library
         produces a system prompt that includes the new mapping too

If any of these steps quietly fails, the user gets a product that
*looks* like it has a library feature but doesn't actually compound.
This test is the safety net.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from clearscript.providers.base import ChatMessage, ChatResponse


class CapturingProvider:
    """Records every system prompt the pipeline sends so we can assert
    library context was actually injected.

    Returns a configurable response so each test step can simulate the
    LLM emitting suggestions / behaving differently on repeat runs.
    """

    name = "capturing"

    def __init__(self) -> None:
        self.calls: list[list[ChatMessage]] = []
        # Default response — first call yields the Tavily/Tabby suggestion.
        self.queue: list[str] = []

    def _next_response(self) -> str:
        if self.queue:
            return self.queue.pop(0)
        # Fallback: trivial three-section response.
        return (
            "cleaned\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]"
        )

    def chat(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(list(messages))
        text = self._next_response()
        return ChatResponse(
            text=text,
            input_tokens=50,
            output_tokens=25,
            model=model,
            provider=self.name,
            latency_ms=1.0,
        )

    def stream(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        yield self._next_response()

    def chat_with_progress(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(list(messages))
        text = self._next_response()
        yield ("delta", text)
        yield (
            "done",
            ChatResponse(
                text=text,
                input_tokens=50,
                output_tokens=25,
                model=model,
                provider=self.name,
                latency_ms=1.0,
            ),
        )


@pytest.fixture
def loop_client(tmp_path, monkeypatch):
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

    provider = CapturingProvider()
    monkeypatch.setattr("clearscript.server.build_provider", lambda _c: provider)

    from clearscript.server import create_app

    app = create_app()
    return TestClient(app), provider


def test_full_compounding_loop(loop_client) -> None:
    """The end-to-end story:

    1. Empty library → first run gets vanilla output, no library context
       injected (beyond the seed pack).
    2. Model emits suggestion ``term: Tavily / Tabby`` → user accepts via
       /api/library/accept-suggestions.
    3. Second run on a transcript that says "Tabby" → system prompt now
       carries the library mapping under "Term mappings from your library".
    4. (Re-run preserves provenance and produces a sibling project.)
    """
    client, provider = loop_client

    # --- Step 1: First run. Model emits a Tavily/Tabby suggestion.
    provider.queue.append(
        "Speaker 1: We use Tavily for search.\n"
        "---CHANGELOG---\n"
        '[{"layer": "L3", "before": "Tabby", "after": "Tavily", "reason": "company"}]\n'
        "---SUGGESTIONS---\n"
        '[{"kind": "term", "canonical": "Tavily", "aliases_seen": ["Tabby"], "type": "company"}]'
    )
    res = client.post(
        "/api/run",
        json={
            "transcript": "Speaker 1: We use Tabby for search.\n",
            "title": "First run",
        },
    )
    assert res.status_code == 200
    first_payload = res.json()
    assert first_payload["suggestions"], "model should have emitted at least one suggestion"
    assert first_payload["project_slug"]

    # --- Step 2: Accept the suggestions.
    accept_res = client.post(
        "/api/library/accept-suggestions",
        json={"suggestions": first_payload["suggestions"]},
    )
    assert accept_res.status_code == 200
    assert accept_res.json()["accepted"]["terms"] >= 1

    # Sanity: library now has the new term.
    listing = client.get("/api/library/terms?q=Tavily").json()["terms"]
    assert any(t["canonical"] == "Tavily" for t in listing)

    # --- Step 3: Second run with a different transcript that ALSO says "Tabby".
    # Track the call count so we can isolate this run's prompt.
    pre_call_count = len(provider.calls)
    provider.queue.append(
        "Speaker 2: Tavily again.\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]"
    )
    res = client.post(
        "/api/run",
        json={
            "transcript": "Speaker 2: We tried Tabby last quarter.\n",
            "title": "Second run",
        },
    )
    assert res.status_code == 200

    # Inspect the system prompt for the second run.
    second_run_calls = provider.calls[pre_call_count:]
    assert second_run_calls, "second run should have invoked the provider"
    second_system_prompt = second_run_calls[0][0].content
    assert "Term mappings from your library" in second_system_prompt
    # The mapping should reference both Tabby and Tavily.
    assert "Tabby" in second_system_prompt
    assert "Tavily" in second_system_prompt


def test_rerun_uses_updated_library(loop_client) -> None:
    """After accepting a suggestion, re-running the ORIGINAL project must
    pick up the new library mapping.

    This is the headline use case for /api/projects/{slug}/rerun: the
    user iterates on the library, then re-runs old transcripts to harvest
    the improvement.
    """
    client, provider = loop_client

    provider.queue.append(
        "Cleaned\n---CHANGELOG---\n[]\n"
        '---SUGGESTIONS---\n[{"kind": "term", "canonical": "Tavily", "aliases_seen": ["Tabby"]}]'
    )
    res = client.post(
        "/api/run", json={"transcript": "Speaker 1: Tabby tools.\n", "title": "Original"}
    )
    orig_slug = res.json()["project_slug"]

    client.post(
        "/api/library/accept-suggestions",
        json={"suggestions": res.json()["suggestions"]},
    )

    # Re-run the original. Library should now carry Tabby → Tavily.
    pre_call_count = len(provider.calls)
    provider.queue.append("Cleaned\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]")
    with client.stream(
        "POST",
        f"/api/projects/{orig_slug}/rerun",
        json={},
    ) as r:
        body = "".join(r.iter_text())
        assert r.status_code == 200, body

    rerun_calls = provider.calls[pre_call_count:]
    assert rerun_calls, "rerun should have invoked the provider"
    rerun_system_prompt = rerun_calls[0][0].content
    assert "Tabby" in rerun_system_prompt
    assert "Tavily" in rerun_system_prompt


def test_seed_pack_terms_already_available_on_fresh_install(loop_client) -> None:
    """The seed pack is supposed to install on first library open so users
    benefit immediately. A run with no prior accepts should still have
    seed pack mappings in the prompt.
    """
    client, provider = loop_client
    provider.queue.append("done\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]")
    client.post(
        "/api/run",
        json={"transcript": "Speaker 1: DeFi is great.\n"},
    )
    # The first prompt the provider saw should mention Dify (seed pack canonical
    # for the alias DeFi).
    first_prompt = provider.calls[0][0].content
    assert "Dify" in first_prompt, "seed pack should auto-install on first library open"
