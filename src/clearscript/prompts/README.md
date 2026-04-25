# Prompt library

This directory contains the LLM prompts that power clearscript's editing pipeline. Prompts are stored as markdown files (not Python strings) so that:

- Non-engineers can read and modify them
- Users can override individual prompts without forking the whole codebase
- Diffs to prompts are reviewable line by line

## Loading order

For a full editing run, the pipeline composes prompts in this order:

```
system_base.md                       # universal system prompt prefix
+ stages/01_prescan.md               # stage-specific instructions
+ layers/l1_speaker.md               # layer specs (loaded as needed)
+ layers/l2_trim.md
+ layers/l3_asr_fix.md
+ layers/l3_5_sentence.md
+ layers/l4_preserve.md
+ layers/l5_format.md
+ layers/l6_punct.md
+ user-provided context briefing
+ chunk content
```

## User overrides

Users can override any prompt by placing a file with the same name under
`~/.config/clearscript/prompts/`. For example, to customize the L3 ASR-fix
layer, create:

```
~/.config/clearscript/prompts/layers/l3_asr_fix.md
```

The user version is loaded if present; otherwise the bundled default is used.

## Editing tips

- Keep prompts short and direct. LLMs follow concise rules better than verbose ones.
- When updating, write the change in the CHANGELOG.md so behavior shifts are tracked.
- Test changes against `tests/fixtures/synthetic/` before opening a PR.
