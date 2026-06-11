# Stage 7: Batch-ask

You receive the consolidated list of items needing user confirmation: ambiguous names, uncertain corrections, conflicting data points, format choices. Present them as a single batch — never interrupt the user multiple times.

## Output format (rendered for the user)

Use the user's primary language (detected from the transcript). Format as a numbered list with:

- A clear location anchor (timestamp or speaker + paragraph number)
- The exact ambiguous text
- The proposed resolution(s)
- A short explanation of why this is being asked

Example (Chinese transcript):

```
本次整理需要你确认 6 处：

1. [00:14:33] "MAM-9" — 是否为 "Mem0"？
   依据: 你在 briefing 提到讨论 Mem0；ASR 在该时段错误率高
   选项: [是 Mem0] [保留 MAM-9] [其他: ___]

2. [00:22:10] 人名 "刘星" — 是否为 briefing 中的某位？
   候选: [刘勋] [刘鑫] [其他: ___] [保留 刘星]

3. [00:31:45 vs 00:48:20] 数据冲突: "千次 query 价格"
   00:31:45: "0.8 元"
   00:48:20: "0.5 元"
   选项: [00:31:45 准] [00:48:20 准] [都保留并标注 [前后口径不一]]

...
```

## Discipline

- **Group related items.** Multiple instances of the same ambiguity get one question, not many.
- **Provide proposed answers, not just questions.** Make it a one-click decision.
- **Order by importance.** Speaker identity > proper nouns > data conflicts > formatting.
- **Be brief.** Each item should fit in 3-4 lines.
