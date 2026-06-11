# L4: Information Preservation

Do not summarize. Do not abstract. Do not "tighten." Transcript value lives in detail, not concision.

## Specific rules

1. **Preserve specific details**:
   - Department names (e.g., "百度网盟", "the platform team")
   - Levels (T8 / P8 / E5)
   - Timelines and dates
   - Performance metrics (3-6-1, OKR results)
   - Headcount, revenue, prices in their original phrasing
   The more granular, the better.

2. **Preserve speaker phrasing for numbers**:
   - "差不多三四百人" stays as-is — do NOT standardize to "约 350 人"
   - "千把万" stays as-is
   - "around 5 to 7 million" stays as-is

3. **Language fidelity** (code-switching):
   - When speakers mix Chinese and English, preserve both verbatim. Do not translate either direction.
   - Industry English terms always stay in English when the speaker said them in English: `ranking`, `PMF`, `cohort`, `churn`, `ARR`, `MRR`, `SaaS`, `GTM`, `NPS`, `burn rate`, `pre-seed`, `Series A/B/C`, `term sheet`, `cap table`, `OKR`, `skip level`, `1-on-1`, `headcount`, `roadmap`, `MVP`, `KPI`, `IC` (individual contributor or investment committee — use context), etc.
   - Heuristic: if the Chinese equivalent would be longer, less natural, or industry-foreign, keep English.

4. **Distinguish two cases that look similar but need opposite treatment**:
   - **Genuine code-switch** ("做 ranking 模型" / "PMF 还没到" / "我们的架构很 scalable" — actually about scalability) → keep as-is
   - **ASR mis-transcription** (Chinese spoken word rendered as English-looking garbage, e.g., ASR turning "技术向" into "技术项" or "skip level" spoken in management context being heard as "scalable") → fix back, that's L3's job

5. **Preserve uncertainty markers**:
   - "好像" / "大概" / "我记得" / "I think" / "if I recall correctly" — keep these. Do not change uncertain language into definitive language.

## Summary

L4 is the "do no harm" layer. Its job is to prevent helpful-looking edits that destroy information. When in doubt about whether an edit removes information, don't make it.
