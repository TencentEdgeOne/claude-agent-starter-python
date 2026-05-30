---
name: web-search
description: Use this skill when the user asks to search the web, look up current information, gather sources, compare recent facts, or answer questions that require external web information. Trigger on phrases such as 网络搜索, 搜索一下, 查一下, 最新, 资料来源, web search, search the web.
---

# Web Search

## Instructions

When this skill is used:

1. Use the available web/search or browser tool to gather information from the web.
2. Prefer multiple credible sources when the question asks for facts, rankings, history, market data, or comparisons.
3. Summarize findings clearly instead of dumping raw search results.
4. Include source names or URLs when available.
5. If data may vary by time, mention the query time or that results are time-sensitive.
6. Do not invent sources, numbers, rankings, or citations.

## Output Format

Return:

```md
## Search Summary

...

## Key Findings

- ...

## Sources

- ...
```

If no reliable source is found, say so directly and suggest a refined query.
