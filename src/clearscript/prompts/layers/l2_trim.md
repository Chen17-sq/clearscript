# L2: Head/Tail Trimming

Strip non-substantive content from the start and end of the transcript.

## Strip

1. **Opening pleasantries**: mic checks, "can you hear me", "who's going first", introductions of the conversation format
2. **Closing farewells**: "bye", "let's add each other on WeChat", "follow-up next week", coordination chitchat
3. **AI-generated content**: any summary, abstract, key-takeaway block injected by Typeless / Yuanbao / Tongyi / Miaoji / Claude. These tools love to prepend "本次访谈总结" / "Meeting Summary" / "Key Takeaways" — delete without exception.

## Keep range

From the **first substantive question or statement** to the **last substantive answer**.

## Edge case: chitchat that looks tangential but isn't

Keep — do not strip — content that looks like chitchat but encodes signal:

- Offhand real reasons for leaving a job
- Candid evaluations of former colleagues or competitors
- Throwaway remarks about industry trends
- Side comments during meetings

These are often the highest-density parts of a transcript. Pure family talk or weather can go.

## Example AI summary patterns to strip

- `## Summary` / `## 摘要` / `## 会议总结` / `## 本次访谈要点` blocks at the top
- "Generated on YYYY-MM-DD by [tool]" footers
- "本次会议共 N 分钟，参会人数 N 人" preamble blocks
- Bullet-point key-takeaway lists prepended before the actual transcript begins
