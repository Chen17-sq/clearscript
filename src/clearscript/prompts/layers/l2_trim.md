# L2: Head/Tail Trimming

Strip non-substantive content from the start and end of the **recording**
— not of whatever text you happen to receive.

## Chunk-position rule (read first)

Long transcripts are split into chunks, and the user prompt tells you
which chunk you're editing ("Chunk position: i of N"):

- **First chunk** → trimming the START is allowed; the end is
  mid-conversation, leave it alone.
- **Last chunk** → trimming the END is allowed; the start is
  mid-conversation, leave it alone.
- **Middle chunk** → NO head/tail trimming at all. The "start" of a
  middle chunk is the continuation of the previous sentence — deleting
  it destroys real content. Only the AI-summary-block rule below still
  applies (those can appear anywhere a tool injected them).
- **No chunk position stated** → the text is the whole recording; both
  ends are in scope.

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
