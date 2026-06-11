"""Test the inline-edit auto-save for project transcripts + cost endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from clearscript.config import Config, ProviderConfig
from clearscript.server import create_app
from clearscript.storage import ProjectStore


def _make_test_config(tmp_path: Path) -> Config:
    return Config(
        default_provider="claude",
        providers={
            "claude": ProviderConfig(
                name="claude",
                type="anthropic",
                api_key="test-key",
                default_model="claude-opus-4-7",
            ),
            "deepseek": ProviderConfig(
                name="deepseek",
                type="openai-compat",
                api_key="test-key",
                default_model="deepseek-chat",
                base_url="https://api.deepseek.com/v1",
            ),
            "ollama": ProviderConfig(
                name="ollama",
                type="ollama",
                base_url="http://localhost:11434",
                default_model="qwen2.5:14b",
            ),
        },
        library_path=tmp_path / "library.db",
        projects_root=tmp_path / "projects",
    )


def _patch_config(monkeypatch, tmp_path: Path) -> None:
    cfg = _make_test_config(tmp_path)
    # The server implementation moved to clearscript.api; AppState.cfg()
    # calls load_config/ensure_dirs through the clearscript.api.deps module.
    monkeypatch.setattr("clearscript.api.deps.load_config", lambda: cfg)
    monkeypatch.setattr("clearscript.api.deps.ensure_dirs", lambda c: None)
    cfg.projects_root.mkdir(parents=True, exist_ok=True)
    cfg.library_path.parent.mkdir(parents=True, exist_ok=True)


def _seed_project(projects_root: Path) -> str:
    store = ProjectStore(projects_root)
    p = store.create("editable interview")
    p.save_run(
        title="x",
        format_="txt",
        provider="claude",
        model="opus",
        input_text="raw",
        edited_markdown="ORIGINAL CLEANED",
        change_log=[],
        suggestions=[],
        input_tokens=100,
        output_tokens=50,
    )
    return p.slug


def test_patch_updates_cleaned_markdown(tmp_path: Path, monkeypatch) -> None:
    _patch_config(monkeypatch, tmp_path)
    slug = _seed_project(tmp_path / "projects")

    client = TestClient(create_app())
    res = client.patch(
        f"/api/projects/{slug}/transcript",
        json={"cleaned_markdown": "USER EDITED VERSION"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["slug"] == slug

    project = ProjectStore(tmp_path / "projects").open(slug)
    assert project.cleaned_md_path.read_text(encoding="utf-8") == "USER EDITED VERSION"


def test_patch_unknown_slug_returns_404(tmp_path: Path, monkeypatch) -> None:
    _patch_config(monkeypatch, tmp_path)

    client = TestClient(create_app())
    res = client.patch(
        "/api/projects/does-not-exist/transcript",
        json={"cleaned_markdown": "x"},
    )
    assert res.status_code == 404


def test_patch_invalidates_cached_docx(tmp_path: Path, monkeypatch) -> None:
    _patch_config(monkeypatch, tmp_path)
    slug = _seed_project(tmp_path / "projects")
    project = ProjectStore(tmp_path / "projects").open(slug)
    project.cleaned_docx_path.write_bytes(b"stale fake docx")
    assert project.cleaned_docx_path.is_file()

    client = TestClient(create_app())
    res = client.patch(
        f"/api/projects/{slug}/transcript",
        json={"cleaned_markdown": "fresh content"},
    )
    assert res.status_code == 200
    assert not project.cleaned_docx_path.is_file()


def test_estimate_cost_endpoint(tmp_path: Path, monkeypatch) -> None:
    _patch_config(monkeypatch, tmp_path)

    client = TestClient(create_app())
    res = client.post(
        "/api/estimate-cost",
        json={"transcript": "X" * 4000, "provider": "deepseek", "model": "deepseek-chat"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["pricing_known"] is True
    assert data["input_tokens"] > 800
    assert data["total_cost_usd"] >= 0
    assert data["model"] == "deepseek-chat"


def test_estimate_cost_unknown_provider_400(tmp_path: Path, monkeypatch) -> None:
    _patch_config(monkeypatch, tmp_path)

    client = TestClient(create_app())
    res = client.post(
        "/api/estimate-cost",
        json={"transcript": "x" * 100, "provider": "imaginary-provider"},
    )
    assert res.status_code == 400
