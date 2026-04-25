# Stage 8: Re-scan after user confirmation

Once the user answers the batch-ask questions, apply their decisions and **re-scan the entire transcript** to catch the same ambiguities elsewhere.

For example: the user confirms "MAM-9 → Mem9" at 00:14:33. You must now search the rest of the document for any other variant of MAM-9 (`MAM9`, `Mam-9`, `妈姆 9`) and apply the same fix consistently. The same applies to confirmed speaker names, company names, and data conflicts.

## Output format

Return the final transcript markdown plus an addendum change log of all edits applied during re-scan:

```json
[
  {
    "stage": "rescan",
    "old": "MAM9",
    "new": "Mem9",
    "reason": "applied user-confirmed mapping from batch-ask",
    "based_on_confirmation": "MAM-9 → Mem9"
  }
]
```

## Discipline

- **Re-scan only applies user-confirmed mappings.** Don't introduce fresh interpretations at this stage.
- **Apply mappings broadly but check context.** "Eileen" should not become "Mem9" because they're not related — only apply each confirmation to its semantic neighborhood.
- **Log every re-scan edit.** They're typically the highest-confidence changes in the document; the user should still be able to audit them.
