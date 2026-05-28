---
name: smart-translator
description: Translate text between Chinese and English while preserving tone, formatting, terminology, and Markdown structure. Use when the user asks to translate, localize, polish bilingual content, or adapt copy for product pages.
---

# Smart Translator

## Instructions

When translating or localizing text:

1. Detect the source language automatically.
2. Translate Chinese to English, or English to Chinese, unless the user specifies another target language.
3. Preserve Markdown, lists, tables, inline code, links, placeholders, and product names.
4. Keep technical terms accurate and consistent.
5. Adapt the tone according to the user's request.
6. If the user does not specify a tone, use a clear, professional, and concise tone.
7. Do not add unrelated explanation.

## Output Format

Return:

```md
## Translation

...

## Notes

- ...
```

Only include `Notes` when there are important terminology, tone, or localization decisions.

## Rules

- Do not change product names unless explicitly requested.
- Preserve placeholders, variables, command names, API names, and code identifiers.
- Preserve Markdown structure whenever possible.
- Keep the translation natural rather than literal when product copy requires localization.
- Respond in the same language as the user unless the user asks otherwise.
