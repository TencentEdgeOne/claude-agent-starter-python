---
name: code-review
description: Review code for quality, bugs, performance issues, and best practices. Use when the user asks to review, audit, or check code quality.
---

# Code Review

## Instructions

When reviewing code, follow these steps:

1. Read the target file(s) using the Read tool
2. Analyze for the following categories:
   - **Bugs & Logic Errors** — Null checks, off-by-one, race conditions
   - **Security** — Injection, hardcoded secrets, missing validation
   - **Performance** — Unnecessary iterations, memory leaks, N+1 queries
   - **Readability** — Naming, function length, dead code
   - **Best Practices** — Error handling, typing, documentation

3. Output a structured review in this format:

## Review Summary

| Category | Issues Found | Severity |
|----------|-------------|----------|
| Bugs | ... | High/Medium/Low |
| Security | ... | ... |
| Performance | ... | ... |

## Detailed Findings

### [Category]: [Issue Title]
- **File**: `path/to/file`
- **Line**: XX-YY
- **Severity**: High | Medium | Low
- **Description**: What's wrong
- **Suggestion**: How to fix (with code snippet if helpful)

## Rules

- Always read the actual file content before reviewing
- Be specific — cite line numbers and code snippets
- Prioritize findings by severity (High → Low)
- Suggest fixes, don't just point out problems
- If the code is good, say so — don't invent issues
- Respond in the same language as the user
