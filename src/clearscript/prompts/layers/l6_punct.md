# L6: Punctuation Normalization

Apply punctuation consistently as you go. This layer is mostly mechanical.

## Rules

1. **Chinese full stop** unified to `。` (not `．` or other variants)
2. **Colons** unified to full-width `：` in Chinese context, ASCII `:` in English context. Speaker labels use `：` for Chinese names, `:` for English names, matching what L1 wrote.
3. **Question marks** match the surrounding language: `？` for Chinese, `?` for English.
4. **Commas** match the surrounding language: `，` for Chinese, `,` for English.
5. **Quotation marks**: Chinese `「」` or `""`, English `""`. Don't mix within a sentence.
6. **Don't add 书名号** (`《》`) around things the speaker didn't say with that emphasis.
7. **Don't normalize spoken punctuation habits** — if the speaker speaks in run-on sentences and you've broken them only where ASR clearly missed a boundary, that's it. Don't impose written-prose punctuation on spoken speech.

## Mixed-language sentences

Within a single sentence containing both Chinese and English:

- Use the punctuation matching the dominant language of that sentence
- Don't switch mid-sentence

Example:
- "我觉得 PMF 还没到，需要再迭代两个版本。" (Chinese-dominant — Chinese punctuation throughout)
- "Their GTM strategy basically copied ours, very 没意思." (English-dominant — English punctuation throughout)
