# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

A full-stack Codex Agent starter project deployed on EdgeOne Makers. The frontend is React + Vite + TypeScript; the backend is Python-based EdgeOne Makers that wrap the Codex Agent SDK with SSE streaming.

## Development Commands

```bash
# Install frontend deps
npm install

# Install Python agent deps
pip install -r requirements.txt

# Local development (starts both frontend + backend via EdgeOne CLI)
npm run dev:agents

# Frontend-only dev server (port 5173)
npm run dev

# Build for production
npm run build
```

**Prerequisite:** Codex CLI must be installed globally:
```bash
npm install -g @anthropic-ai/Codex
```

## Architecture

### Frontend (src/)

- **App.tsx** — Main app shell; manages conversation ID (localStorage-persisted), message state, tool lamp animations, and SSE stream lifecycle
- **api.ts** — API client for `/chat` (SSE streaming), `/stop` (abort agent), `/history` (restore messages). SSE parsing with `text_delta`, `tool_called`, `ping`, `done`, `error` events
- **components/CodeViewer.tsx** — Static decorative code panel showing a simplified version of the handler (right side of the page)
- **components/ChatWindow.tsx / ChatInput.tsx** — Chat UI with markdown rendering (react-markdown + remark-gfm)
- **components/ToolIndicators.tsx / ToolLamp.tsx** — Animated indicators that flash when Codex calls a tool

### Backend (agents/)

Python EdgeOne Makers. File path maps directly to route:
- `agents/chat/index.py` → `POST /chat` — Main SSE streaming chat handler
- `agents/stop/index.py` → `POST /stop` — Abort active agent run
- `agents/history/index.py` → `POST /history` — Retrieve conversation history

Private modules (prefixed with `_`, not exposed as routes):
- `agents/_model.py` — Model name resolution and gateway env collection
- `agents/_logger.py` — Logging utility

### Key Patterns

**SSE Protocol:** Backend yields SSE events as an async generator. Events: `text_delta` (streaming text), `tool_called` (tool invocation), `ping` (heartbeat every 5s), `error`, `done`.

**Session Persistence:** `ctx.store.claude_session_store()` preserves Codex SDK transcript across requests. `ctx.store.append_message()` saves user/assistant messages for `/history` recovery.

**Tool Bridge:** EdgeOne platform sandbox tools (commands, files, code_interpreter, browser) are wrapped as `SdkMcpTool` objects, registered on a `create_sdk_mcp_server`, and passed to the Codex Agent SDK via `mcp_servers`.

**Cancellation:** Dual mechanism — frontend `AbortController.abort()` stops SSE reading; backend `context.utils.abort_active_run()` actually interrupts the LLM request.

**Conversation ID:** Passed via `makers-conversation-id` header for chat/history. The `/stop` endpoint receives it in the request body (not header) to avoid overwriting the cancel event.

## Configuration

- `edgeone.json` — Build/deploy config and agent sandbox settings (900s timeout)
- `agents/config.json` — Route mapping for Python functions
- `.env` — Provider config (see `.env.example`). Supports `anthropic_official` (direct) or `ai_gate` (gateway) providers
- `vite.config.ts` — Frontend Vite dev/build configuration

## Styling

CSS Modules throughout (`*.module.css`). The UI uses a dark theme with ambient gradient blobs and a retro-terminal aesthetic for the code viewer panel.
