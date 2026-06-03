# Claude Agent Starter (Python)

A full-stack EdgeOne Makers Agent template powered by Anthropic Claude Agent SDK (Python). Demonstrates how to build a streaming chat Agent with EdgeOne sandbox tools (via MCP), session memory, and real-time tool indicators.

## Deploy

[![Deploy with EdgeOne Pages](https://cdnstatic.tencentcs.com/edgeone/pages/deploy.svg)](https://edgeone.ai/makers/new?template=claude-agent-starter-python&from=within&fromAgent=1&agentLang=python)

## Features

- **SSE Streaming Chat** — Token-by-token `text_delta` push; `tool_called` events when tools are invoked
- **Session Memory** — Saves Claude transcript via `context.store.claude_session_store()` for cross-request context restore
- **EdgeOne Sandbox Tools** — commands, files, code_interpreter, browser — bridged to Claude Agent SDK via MCP Server
- **Stop Generation** — Truly interrupts the LLM call via platform runtime cancel signal
- **Tool Indicators** — 4 animated lamps light up in real time when Claude calls a tool

## Directory Structure

```text
claude-agent-starter-python/
├── agents/                        # Stateful EdgeOne Makers Agent Functions (Python)
│   ├── chat/
│   │   └── index.py              # POST /chat — SSE streaming chat
│   ├── stop/
│   │   └── index.py              # POST /stop — abort active agent run
│   ├── _model.py                 # Model & gateway env config (private module)
│   ├── _logger.py                # Logger utility (private module)
│   ├── config.json               # Route config
│   └── requirements.txt          # Python agent dependencies
├── cloud-functions/               # Stateless EdgeOne Pages Python cloud functions
│   ├── history/
│   │   └── index.py              # POST /history — load conversation messages
│   ├── conversations/
│   │   └── index.py              # POST /conversations — list a user's conversations
│   ├── clear-history/
│   │   └── index.py              # POST /clear-history — clear messages of one conversation
│   ├── delete-conversation/
│   │   └── index.py              # POST /delete-conversation — delete a conversation entirely
│   ├── _logger.py                # Logger utility
│   ├── _redact.py                # Sensitive-field redactor for logs
│   └── requirements.txt          # Python cloud-function dependencies
├── src/                           # React frontend (Vite + TypeScript)
│   ├── App.tsx                    # Main app component
│   ├── api.ts                    # Backend API wrappers (SSE streaming)
│   ├── types.ts                  # Type definitions
│   └── components/               # UI components
│       ├── ChatWindow.tsx        # Chat window
│       ├── ChatBubble.tsx        # Message bubble (Markdown support)
│       ├── ChatInput.tsx         # Input box + presets + stop button
│       ├── CodeViewer.tsx        # Code display panel (CRT aesthetic)
│       ├── ToolIndicators.tsx    # Tool indicator container
│       └── ToolLamp.tsx          # Single tool indicator lamp
├── index.html                    # Entry HTML
├── package.json                  # Frontend dependencies (includes Claude Agent SDK)
├── edgeone.json                  # EdgeOne deployment config
├── vite.config.ts                # Vite config
├── tsconfig.json                 # TypeScript config
└── uv.toml                       # Python package mirror config
```

> Files prefixed with `_` are private modules — not mapped as public routes by EdgeOne.
>
> **Why two backend folders?** `agents/` holds long-running, stateful routes (active SSE streams, per-conversation abort signals); `cloud-functions/` holds short, stateless routes that just read/write `context.agent.store`. Splitting them keeps history/list/delete requests from contending with an active chat for the per-conversation lock.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AI_GATEWAY_API_KEY` | Yes | AI Gateway API key (mapped to `ANTHROPIC_API_KEY` for Claude SDK) |
| `AI_GATEWAY_BASE_URL` | Yes | AI Gateway base URL (mapped to `ANTHROPIC_BASE_URL`) |
| `AI_GATEWAY_MODEL` | No | Model name (default: `hy3-preview`) |
| `AI_GATEWAY_SMALL_MODEL` | No | Small/fast model for internal SDK sub-calls |

## API Endpoints

| Endpoint | Method | Side | Description |
|----------|--------|------|-------------|
| `/chat` | POST | `agents/` | SSE streaming chat. Header: `makers-conversation-id` |
| `/stop` | POST | `agents/` | Abort the active agent run. Body: `{ "conversation_id": "..." }` |
| `/history` | POST | `cloud-functions/` | Get conversation history. Body: `{ "conversation_id": "..." }` |
| `/conversations` | POST | `cloud-functions/` | List a user's conversations (paginated). Body: `{ "user_id": "...", "limit"?: 20, "after"?: "...", "before"?: "...", "order"?: "desc" }` |
| `/clear-history` | POST | `cloud-functions/` | Clear all messages of one conversation. Body: `{ "conversation_id": "..." }` |
| `/delete-conversation` | POST | `cloud-functions/` | Permanently delete a conversation. Body: `{ "conversation_id": "..." }` |

### SSE Events

```
event: text_delta     data: {"delta":"Hello"}
event: tool_called    data: {"tool":"commands"}
event: ping           data: {"ts":1710000000000}
event: error          data: {"message":"..."}
event: done           data: {"stopped":false}
```

## Architecture

### Backend (`agents/` + `cloud-functions/`)

`agents/` is where the stateful work happens — it owns the live SSE stream and the AbortSignal for the running model call:

1. **`collect_gateway_env()`** — Maps `AI_GATEWAY_*` env vars to `ANTHROPIC_*` for the Claude Agent SDK subprocess
2. **`context.tools.all()`** — Extracts EdgeOne sandbox tools and wraps them as Claude MCP tools
3. **`create_sdk_mcp_server()`** — Registers EdgeOne tools as an MCP Server for the Claude Agent SDK
4. **`context.store.claude_session_store()`** — Provides session persistence for multi-turn memory
5. **`query(prompt, options)`** — Launches the Claude Agent with streaming output
6. **`store.append_message()`** — Saves user/assistant messages so they can be restored later

`cloud-functions/` handles the stateless conversation-store CRUD (history / conversations / clear-history / delete-conversation). They read/write `context.agent.store` directly without spinning up an agent run, so they don't compete with active chats for the per-conversation lock.

### Frontend (`src/`)

- `App.tsx` — Orchestrates chat panel + code viewer, manages SSE stream
- `api.ts` — SSE parsing, dispatches `onTextDelta`, `onToolCalled`, `onDone`, `onError`
- `components/CodeViewer.tsx` — Static code display panel (amber CRT aesthetic) showing the agent flow
- `components/ToolIndicators.tsx` — Animated tool lamps that flash when Claude calls a tool

## Local Development

```bash
# Install frontend dependencies
npm install

# Install backend Python dependencies
pip install -r requirements.txt

# Start EdgeOne local dev (frontend + backend)
edgeone makers dev
```
