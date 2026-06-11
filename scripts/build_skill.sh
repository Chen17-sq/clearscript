#!/usr/bin/env bash
# Build clearscript.skill — a self-contained .skill bundle for Claude Code,
# Claude Agent SDK, or any agent that loads markdown-formatted skills.
#
# Output: dist/clearscript.skill (a zip)
#
# Source-of-truth for the prompts is src/clearscript/prompts/ — the same
# files the standalone app loads at runtime. So a prompt improvement in
# the main package automatically improves the skill on next build.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DIST="$ROOT/dist"
STAGING="$DIST/clearscript"

# Clean ONLY our own outputs. `rm -rf "$DIST"` used to wipe the wheel and
# sdist that `uv build` had just produced — every GitHub release shipped
# without installable artifacts because of that line.
echo "→ cleaning skill staging + previous bundle"
rm -rf "$STAGING" "$DIST/clearscript.skill"
mkdir -p "$STAGING/prompts" "$STAGING/scripts" "$STAGING/references"

echo "→ copying SKILL.md"
cp "$ROOT/skill/SKILL.md" "$STAGING/SKILL.md"

echo "→ copying prompts (single source of truth: src/clearscript/prompts/)"
cp -R "$ROOT/src/clearscript/prompts/." "$STAGING/prompts/"
# Strip Python machinery and engineer-only files — agents don't load these
rm -f "$STAGING/prompts/README.md"
rm -f "$STAGING/prompts/__init__.py"
find "$STAGING/prompts" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$STAGING/prompts" -type f -name "*.pyc" -delete

echo "→ copying reference templates"
cp "$ROOT/skill/references/"*.md "$STAGING/references/"

echo "→ copying optional scripts"
cp "$ROOT/src/clearscript/export/docx.py" "$STAGING/scripts/to_docx.py"

echo "→ packing dist/clearscript.skill"
cd "$DIST"
zip -qr clearscript.skill clearscript/
cd "$ROOT"

SIZE=$(wc -c < "$DIST/clearscript.skill" | tr -d ' ')
echo ""
echo "✓ built $DIST/clearscript.skill ($SIZE bytes)"
echo ""
echo "Install for Claude Code:"
echo "  mkdir -p ~/.claude/skills"
echo "  unzip -o $DIST/clearscript.skill -d ~/.claude/skills/"
echo ""
echo "Or in any agent that loads .skill files: drop in your agent's skill dir."
