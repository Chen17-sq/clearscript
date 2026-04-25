# Stage 6: Self-review

After all chunks have been edited and stitched, you receive the full edited transcript along with the cumulative change log. Your job is to QA your own work before the user is asked to confirm anything.

Look for:

1. **Speaker label inconsistencies.** Same person rendered differently across the document.
2. **Residual ASR errors.** Patterns the per-chunk passes might have missed.
3. **Cross-document data conflicts.** Same metric mentioned with different numbers in different places.
4. **Format residue.** Bullet style mixing, leftover `[Speaker N]` labels, mixed punctuation.
5. **Over-corrections.** Places where you may have rewritten for fluency rather than fixed an error. Roll those back if confidence is low.
6. **Suspicious fixes.** Changes you made with `confidence < 0.7` that should be promoted to user review.

## Output format (JSON)

```json
{
  "additional_corrections": [
    {"layer": "L1", "old": "...", "new": "...", "reason": "..."}
  ],
  "rollbacks": [
    {"original_change_id": "abc123", "reason": "low-confidence fluency edit, restoring original"}
  ],
  "promotions_to_user_review": [
    {"location": "Speaker 2 段落 3", "issue": "...", "options": ["A", "B"]}
  ],
  "data_conflicts": [
    {"locations": ["00:14:30", "00:48:20"], "metric": "千次 query 价格", "values": ["0.8 元", "0.5 元"]}
  ],
  "format_issues": []
}
```

## Discipline

- **Self-review is for catching mistakes, not for second-guessing high-confidence edits.** Don't undo correct work.
- **Be honest about uncertainty.** Promoting an edit to user review is a feature, not a failure.
- **Don't introduce new edits without logging them.**
