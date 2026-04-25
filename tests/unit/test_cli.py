"""CLI smoke tests."""

from __future__ import annotations

from typer.testing import CliRunner

from clearscript import __version__
from clearscript.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_providers_lists_default_providers() -> None:
    result = runner.invoke(app, ["providers"])
    assert result.exit_code == 0
    assert "claude" in result.stdout
    assert "ollama" in result.stdout
