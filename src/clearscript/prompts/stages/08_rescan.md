# Stage 8: Re-scan after user confirmation

Once the user answers the batch-ask questions, apply their decisions and **re-scan the entire transcript** to catch the same ambiguities elsewhere.

For example: the user confirms "MAM-9 → Mem0" at 00:14:33. You must now search the rest of the document for any other variant of MAM-9 (`MAM9`, `Mam-9`, `妈姆 9`) and apply the same fix consistently. The same applies to confirmed speaker names, company names, and data conflicts.

## Output format

Use the SAME three-section contract as Stage 4: the final transcript
markdown first, then `---CHANGELOG---` on its own line, then the JSON
array of re-scan edits, then `---SUGGESTIONS---` and a JSON array (or
`[]`). Re-scan changelog entries carry `"stage": "rescan"`:

```json
[
  {
    "stage": "rescan",
    "old": "MAM9",
    "new": "Mem0",
    "reason": "applied user-confirmed mapping from batch-ask",
    "based_on_confirmation": "MAM-9 → Mem0"
  }
]
```

## Discipline

- **Re-scan only applies user-confirmed mappings.** Don't introduce fresh interpretations at this stage.
- **Apply mappings broadly but check context.** "Eileen" should not become "Mem0" because they're not related — only apply each confirmation to its semantic neighborhood.
- **Log every re-scan edit.** They're typically the highest-confidence changes in the document; the user should still be able to audit them.
