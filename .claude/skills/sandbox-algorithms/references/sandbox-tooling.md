# Sandbox Tooling Reference

The EdgeOne Pages Agent Toolkit exposes sandbox execution through `context.sandbox` and `context.tools`.

For Claude Agent SDK, tools are usually registered through `context.tools.toClaudeMcpServer()`.

The relevant MCP tool is `code_interpreter`, usually exposed to Claude as `mcp__edgeone__code_interpreter`.

Arguments:

```json
{
  "language": "python",
  "code": "print(1 + 1)",
  "timeout": 10
}
```

Use Python for deterministic algorithm tasks unless the user asks for another language.
