# Claude Agent Starter (Python)

**Language:** English | [简体中文](./README_zh-CN.md)

A full-stack EdgeOne Makers Agent template — streaming chat backed by the Claude Agent SDK (Python), with EdgeOne sandbox tools wired in via MCP and conversation memory persisted through `context.agent.store`.

**Framework:** Claude Agent SDK · **Category:** Quick Start <!-- TODO: confirm --> · **Language:** Python

[![Deploy to EdgeOne Makers](https://cdnstatic.tencentcs.com/edgeone/pages/deploy.svg)](https://edgeone.ai/makers/new?template=claude-agent-starter-python&from=within&fromAgent=1&agentLang=python)

<!-- ![preview](./assets/preview.png)  TODO: confirm -->

## Overview

A minimal, production-shaped Python starter that wires the Claude Agent SDK into EdgeOne Makers. Demonstrates the full chat loop — SSE streaming, sandbox tool calls, conversation persistence — so you can fork it and start replacing prompts and tools instead of plumbing.

- **SSE streaming chat** — token-by-token `text_delta` events, plus `tool_called` events whenever the model invokes a tool.
- **Sandbox tools via MCP** — `commands`, `files`, `code_interpreter`, `browser` are wrapped as `SdkMcpTool`s and registered through `create_sdk_mcp_server`, then handed to Claude via `mcp_servers`.
- **Sticky conversation memory** — Claude transcript stored in `context.store.claude_session_store()`; user/assistant messages mirrored via `store.append_message()` for replayable history.
- **Dual cancellation** — frontend `AbortController` plus backend `context.utils.abort_active_run()` so `/stop` actually interrupts the LLM call.
- **Two-folder backend** — long-running stateful work in `agents/`, short stateless CRUD in `cloud-functions/`.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AI_GATEWAY_API_KEY` | Yes | Model gateway API key. Use your Makers Models API Key, or any OpenAI-compatible provider key. |
| `AI_GATEWAY_BASE_URL` | Yes | Gateway base URL. For Makers Models, use `https://ai-gateway.edgeone.link/v1`. |
| `AI_GATEWAY_MODEL` | No | Model ID. Defaults to `@makers/deepseek-v4-flash` (a free built-in model). |

This template follows the OpenAI-compatible standard — point these at Makers Models or any compatible provider.

### How to get `AI_GATEWAY_API_KEY`

1. Open the [Makers Console](https://console.cloud.tencent.com/edgeone/makers).
2. Sign in and enable Makers.
3. Go to **Makers → Models → API Key** and create a key.
4. Copy it into `AI_GATEWAY_API_KEY`.

The built-in `@makers/deepseek-v4-flash` model is free with a usage cap and is suitable for prototyping. For production, bind your own paid provider (BYOK).

### Provider fallbacks

`agents/_model.py` also reads `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` / `ANTHROPIC_CUSTOM_HEADERS` directly — useful if you want to call the Anthropic API instead of going through a gateway. If both sets are present, the gateway variables take precedence. Set `AI_GATEWAY_SMALL_MODEL` (or `ANTHROPIC_SMALL_FAST_MODEL`) to override the small model the SDK uses for internal sub-calls.

## Local Development

Prerequisites: Node.js ≥ 18, Python ≥ 3.10, and the EdgeOne CLI (`npm i -g edgeone`).

```bash
npm install
pip install -r agents/requirements.txt
cp .env.example .env       # then fill in AI_GATEWAY_API_KEY / AI_GATEWAY_BASE_URL
edgeone makers dev
```

Local agent metrics & traces are exposed at `http://localhost:8080/agent-metrics`.

## Project Structure

```text
claude-agent-starter-python/
├── agents/                          # Stateful EdgeOne Makers Agent Functions (Python)
│   ├── chat/index.py               # POST /chat — SSE streaming chat
│   ├── stop/index.py               # POST /stop — abort active agent run
│   ├── _model.py                   # Model & gateway env config (private)
│   ├── _logger.py                  # Logger utility (private)
│   ├── config.json                 # Route config
│   └── requirements.txt            # Python agent dependencies
├── cloud-functions/                 # Stateless EdgeOne Pages Python cloud functions
│   ├── history/index.py            # POST /history — load conversation messages
│   ├── conversations/index.py      # POST /conversations — list a user's conversations
│   ├── clear-history/index.py      # POST /clear-history — clear messages of one conversation
│   ├── delete-conversation/index.py # POST /delete-conversation — delete a conversation entirely
│   ├── _logger.py                  # Logger utility
│   ├── _redact.py                  # Sensitive-field redactor for logs
│   └── requirements.txt            # Python cloud-function dependencies
├── src/                             # React + Vite + TypeScript frontend
│   ├── App.tsx                     # Conversation ID + SSE stream orchestration
│   ├── api.ts                      # /chat, /stop, /history, ... wrappers and SSE parser
│   └── components/                 # ChatWindow, ChatInput, CodeViewer, ToolIndicators, ...
├── package.json                     # Frontend dependencies
├── edgeone.json                     # EdgeOne deployment config
├── .env.example                     # Environment variables template
├── vite.config.ts
└── tsconfig.json
```

> Files prefixed with `_` are private modules — not exposed as public routes.

## Resources

- [EdgeOne Makers Agents — Documentation](https://pages.edgeone.ai/document/agents)
- [EdgeOne Makers — Quick Start](https://pages.edgeone.ai/document/agents-quickstart)
- [Makers Models](https://pages.edgeone.ai/document/models)

## License

MIT.
