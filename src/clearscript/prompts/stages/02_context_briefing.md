# Stage 2: Context Briefing

This stage produces five questions for the user to answer before editing begins. The user's answers seed the editing pipeline with high-confidence anchors.

If pre-scan results are available, pre-fill suggested answers. The user can accept or override each.

## Output format (JSON)

```json
{
  "questions": [
    {
      "id": "scenario_type",
      "label": "What is the scenario type?",
      "options": ["VC reference check", "Founder interview", "Customer interview", "Internal meeting", "Investment committee", "Podcast", "Media interview", "Other"],
      "suggested": "VC reference check",
      "required": true
    },
    {
      "id": "speakers",
      "label": "Who are the main speakers? (Real name + role/affiliation)",
      "input_type": "list",
      "suggested": ["Speaker 1 = ?", "Speaker 2 = ?"],
      "required": true
    },
    {
      "id": "entities",
      "label": "What companies, products, or proper nouns appear in the conversation? (Comma-separated; these become seeds for terminology lookup)",
      "input_type": "text",
      "suggested": "",
      "required": false
    },
    {
      "id": "domain",
      "label": "What professional domain best describes this conversation?",
      "options": ["Venture capital", "AI infrastructure", "Consumer", "Enterprise SaaS", "Medical", "Legal", "Crypto", "Hardware", "Education", "Other"],
      "suggested": null,
      "required": false
    },
    {
      "id": "key_dates",
      "label": "Key dates or project codenames worth preserving exactly?",
      "input_type": "text",
      "suggested": "",
      "required": false
    }
  ]
}
```

## Guidelines

- Phrase questions in the user's UI language (zh or en, detected from the transcript).
- Always offer a "Skip / I'll provide minimal context" path. Do not block the pipeline if the user declines to answer.
- Suggested answers should be generated from the pre-scan output, not from your prior knowledge.
