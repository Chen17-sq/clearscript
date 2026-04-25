# Stage 1: Pre-scan

You will receive a raw ASR transcript. Read the entire document once and produce a structured summary that the next stages will use to plan editing.

## Output format (JSON)

Return a single JSON object with this shape:

```json
{
  "estimated_speaker_count": 2,
  "detected_speaker_labels": ["Speaker 1", "Speaker 2", "[Aldrich]"],
  "estimated_duration_minutes": 90,
  "approximate_word_count": 12500,
  "primary_languages": ["zh", "en"],
  "code_switch_density": "high",
  "domain_signals": ["venture capital", "AI infrastructure"],
  "candidate_proper_nouns": ["Dify", "Manus", "MAM-9", "Eileen"],
  "candidate_acronyms": ["PMF", "GTM", "SaaS"],
  "potential_high_error_zones": [
    {"approximate_location": "0:14:30", "reason": "rapid technical jargon cluster"},
    {"approximate_location": "0:42:00", "reason": "phone audio quality drop"}
  ],
  "structural_issues": [
    "AI-generated summary block at top of transcript (will need stripping)",
    "Last 3 minutes appear to be off-topic farewells"
  ],
  "notes": "Brief free-text observations the user might find useful at the briefing stage."
}
```

## Guidelines

- **Be conservative on speaker count.** ASR often splits one speaker into multiple labels. If two labels share style and topic, count them as one.
- **Candidate proper nouns** should be tokens that look like names, products, or companies — they will be cross-checked against the user's library.
- **Domain signals** should be 1-3 short phrases describing the conversation topic — these guide which terminology subset to load.
- Do not edit the transcript at this stage. Pre-scan is read-only.
