# 从 `claude-agent-starter` 同步会话管理功能

目标项目：`/Users/wenyiqing/Desktop/agents/agent-example/claude-agent-starter-python`

参考项目：`/Users/wenyiqing/Desktop/agents/agent-example/claude-agent-starter`

---

## 功能概览

本次要同步的功能是**多会话管理**，涉及：

1. 稳定用户 ID（`eo-uuid`）
2. 左侧会话列表侧栏（ConversationSidebar）
3. 会话创建 / 切换 / 删除
4. 后端新增 `/conversations` 和 `/delete-conversation` 两个 API
5. 现有 `/chat`、`/history`、`/clear-history` 透传 `userId`
6. 侧栏乐观更新（流式首帧立刻出现新会话）
7. 三栏布局（sidebar + chat + code/debug）

---

## 一、前端变更

前端代码结构与 TS 版项目完全一致（均为 React + TypeScript + CSS Modules），可以**直接复制**源文件并按下文说明做最小适配。

### 1.1 新增 / 修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/types.ts` | **修改** | 新增 3 个类型 |
| `src/api.ts` | **修改** | 新增 2 个 API 路由 + 2 个函数，修改 3 个已有函数签名 |
| `src/i18n/zh.ts` | **修改** | 新增侧栏中文文案 |
| `src/i18n/en.ts` | **修改** | 新增侧栏英文文案 |
| `src/components/ConversationSidebar.tsx` | **新增** | 左侧会话列表组件 |
| `src/components/ConversationSidebar.module.css` | **新增** | 侧栏样式 |
| `src/App.tsx` | **修改** | 状态重构、eoUuid、侧栏接入、乐观更新 |
| `src/App.module.css` | **修改** | 双栏改三栏 |

> 建议操作：直接把 `claude-agent-starter` 中以上文件全部复制过来覆盖，然后再检查下面列出的差异项。

---

### 1.2 `src/types.ts` — 新增类型

在文件末尾，`ToolLampState` 之后追加：

```ts
export interface ConversationSummary {
  id: string;
  title: string;
  preview?: string;
  lastMessageAt?: number;
  createdAt?: number;
  userId?: string;
  messageCount?: number;
}

export interface ListConversationsParams {
  userId: string;
  limit?: number;
  order?: 'asc' | 'desc';
  after?: string;
  before?: string;
}

export interface ListConversationsResponse {
  conversations: ConversationSummary[];
  nextCursor?: string;
  previousCursor?: string;
}
```

---

### 1.3 `src/api.ts` — 新增路由与函数

**（a）路由常量**

```ts
export const API = {
  chat: '/chat',
  chatStop: '/stop',
  history: '/history',
  clearHistory: '/clear-history',
  conversations: '/conversations',           // 新增
  deleteConversation: '/delete-conversation', // 新增
} as const;
```

**（b）修改 `fetchConversationHistory` 签名**（新增可选 `userId` 参数，传入请求体）

```ts
export async function fetchConversationHistory(
  conversationId: string,
  userId?: string,
): Promise<Message[]>
```

请求体改为：
```ts
body: JSON.stringify({ conversation_id: conversationId, user_id: userId }),
```

**（c）修改 `sendMessageStream` 签名**（新增可选 `userId` 参数）

```ts
export function sendMessageStream(
  message: string,
  callbacks: StreamCallbacks,
  conversationId?: string,
  messageIds?: { userMsgId: string; botMsgId: string },
  userId?: string,   // 新增
): AbortController
```

请求体加上 `userId`：
```ts
body: JSON.stringify({
  message,
  userMsgId: messageIds?.userMsgId,
  botMsgId: messageIds?.botMsgId,
  userId,   // 新增
}),
```

**（d）修改 `clearConversationHistory` 签名**（新增可选 `userId`）

```ts
export async function clearConversationHistory(
  conversationId?: string,
  userId?: string,  // 新增
): Promise<boolean>
```

请求体改为：
```ts
body: JSON.stringify({ conversation_id: conversationId, user_id: userId }),
```

**（e）新增 `listConversations`**

```ts
import type { ..., ListConversationsParams, ListConversationsResponse } from './types';

export async function listConversations(
  params: ListConversationsParams,
): Promise<ListConversationsResponse> {
  const empty: ListConversationsResponse = { conversations: [] };
  if (!params.userId) return empty;

  try {
    const res = await fetch(API.conversations, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: params.userId,
        limit: params.limit ?? 20,
        order: params.order ?? 'desc',
        after: params.after,
        before: params.before,
      }),
    });
    if (!res.ok) return empty;
    const data = await res.json().catch(() => null) as ListConversationsResponse | null;
    if (!data || !Array.isArray(data.conversations)) return empty;
    return {
      conversations: data.conversations,
      nextCursor: data.nextCursor,
      previousCursor: data.previousCursor,
    };
  } catch {
    return empty;
  }
}
```

**（f）新增 `deleteConversation`**

```ts
export async function deleteConversation(
  conversationId: string,
  userId?: string,
): Promise<boolean> {
  if (!conversationId) return false;
  try {
    const res = await fetch(API.deleteConversation, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId, user_id: userId }),
    });
    return res.ok;
  } catch {
    return false;
  }
}
```

---

### 1.4 i18n — 新增侧栏文案

**`src/i18n/zh.ts`** 末尾（`lang.switch` 之后）追加：

```ts
// Sidebar
"sidebar.label": "会话列表",
"sidebar.title": "会话",
"sidebar.newChat": "新建聊天",
"sidebar.loading": "正在加载会话...",
"sidebar.loadMore": "加载更多",
"sidebar.loadingMore": "加载中...",
"sidebar.emptyTitle": "暂无会话",
"sidebar.emptyHint": "点击「新建聊天」开始第一段对话。",
"sidebar.delete": "删除会话",
"sidebar.deleteConfirm": "确定要永久删除这个会话吗？此操作不可恢复。",
```

**`src/i18n/en.ts`** 末尾（`lang.switch` 之后）追加：

```ts
// Sidebar
"sidebar.label": "Conversation list",
"sidebar.title": "Chats",
"sidebar.newChat": "New chat",
"sidebar.loading": "Loading conversations...",
"sidebar.loadMore": "Load more",
"sidebar.loadingMore": "Loading...",
"sidebar.emptyTitle": "No conversations yet",
"sidebar.emptyHint": "Click \"New chat\" to start your first conversation.",
"sidebar.delete": "Delete conversation",
"sidebar.deleteConfirm": "Permanently delete this conversation? This cannot be undone.",
```

---

### 1.5 ConversationSidebar 组件

直接从 `claude-agent-starter` 复制：

- `src/components/ConversationSidebar.tsx`
- `src/components/ConversationSidebar.module.css`

无需修改。

---

### 1.6 `src/App.tsx` — 完整替换

直接从 `claude-agent-starter` 复制 `src/App.tsx`。

该文件包含以下所有逻辑，无需手动改写：

- `getOrCreateEoUuid()`：从 `localStorage['eo-uuid']` 读取或 `crypto.randomUUID()` 创建稳定用户 ID
- `eoUuidRef`：在整个组件生命周期内保持不变的 ref
- `activeConversationId` state（代替原来只使用 ref）
- `loadConversation(convId)`：抽离的会话恢复逻辑（可复用于切换/初始化）
- `refreshConversations(mode, cursor)`：分页刷新侧栏
- `handleSelectConversation`：切换会话
- `handleCreateConversation`：新建会话
- `handleDeleteConversation`：乐观删除（立即移除 UI，fire-and-forget 后端请求）
- `handleLoadMoreConversations`：加载更多
- `handleSend` 中的 `primeSidebar()`：首帧 SSE 触发乐观插入新会话
- `ConversationSidebar` 挂入三栏布局

**注意**：Python 版项目的 `App.tsx` 目前没有 `hadExistingConversationIdRef`，而是直接用 `getExistingConversationId()`，新版用 `loadConversation()` 统一处理，逻辑一致。

---

### 1.7 `src/App.module.css` — 三栏布局

直接从 `claude-agent-starter` 复制覆盖。

关键改动：
- `.stage` 最大宽度从 `1280px` 增到 `1440px`
- `.chatPanel` 从 `flex: 0 0 58%` 改为 `flex: 1 1 auto`（自适应）
- `.codePanel` 从 `flex: 0 0 42%` 改为 `flex: 0 0 38%`
- 新增 `@media (max-width: 900px)` 下隐藏 `.codePanel`

---

## 二、后端变更

Python 版后端位于 `agents/`（Python）和 `cloud-functions/`（TypeScript）。

新增的两个 API 都是纯**会话索引**操作（不需要 Claude SDK），用 Python 还是 TypeScript 均可。建议与现有文件保持语言一致：

- 现有 Python agent 目录下已有 `chat/`, `stop/`, `clear-history/`, `history/`
- 建议新增 Python handler 放在 `agents/conversations/` 和 `agents/delete-conversation/`

### 2.1 新增 `agents/conversations/index.py` — 列出会话

路由：**POST `/conversations`**

```python
"""
Conversations handler — EdgeOne Makers

Route: POST /conversations

Lists conversations for the requesting eo-uuid user.
Calls context.store.list_conversations(user_id=..., limit=..., order=..., after=..., before=...).
Returns: { conversations, next_cursor, previous_cursor }

user_id is REQUIRED — returns 400 without it.
"""

from typing import Any
from .._logger import create_logger

logger = create_logger("conversations")

DEFAULT_LIMIT = 20
MIN_LIMIT = 1
MAX_LIMIT = 100


def _clamp_limit(raw) -> int:
    try:
        v = int(raw)
        return max(MIN_LIMIT, min(MAX_LIMIT, v))
    except (TypeError, ValueError):
        return DEFAULT_LIMIT


def _normalize_conversation(item: Any) -> dict | None:
    """Normalize a runtime conversation object into a stable frontend shape."""
    if item is None:
        return None

    # Support both object attributes and dict keys
    def get(key, *aliases):
        for k in (key, *aliases):
            v = getattr(item, k, None) if not isinstance(item, dict) else item.get(k)
            if v is not None:
                return v
        return None

    conv_id = get("id", "conversation_id", "conversationId")
    if not conv_id:
        return None

    # Build title from first user message preview if no explicit title
    explicit_title = get("title", "name", "subject")
    first_question = get(
        "first_user_message", "firstUserMessage",
        "first_message", "firstMessage",
    )
    if not explicit_title and first_question:
        text = str(first_question).replace("\n", " ").strip()
        if len(text) <= 8:
            explicit_title = text
        elif text:
            explicit_title = text[:8] + "..."
    title = explicit_title or "New chat"

    preview = get("preview", "last_message", "lastMessage", "snippet", "summary")

    def to_ts(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return int(v)
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    return {
        "id": str(conv_id),
        "title": title,
        "preview": str(preview) if preview else None,
        "lastMessageAt": to_ts(get("last_message_at", "lastMessageAt", "updated_at", "updatedAt")),
        "createdAt": to_ts(get("created_at", "createdAt")),
        "userId": str(u) if (u := get("user_id", "userId")) else None,
        "messageCount": int(mc) if (mc := get("message_count", "messageCount")) else None,
    }


async def handler(context: Any):
    body = getattr(context.request, "body", None) or {}
    if not isinstance(body, dict):
        body = {}

    user_id = str(body.get("user_id") or body.get("userId") or "").strip()
    limit = _clamp_limit(body.get("limit", DEFAULT_LIMIT))
    order = "asc" if body.get("order") == "asc" else "desc"
    after = str(body.get("after") or "").strip() or None
    before = str(body.get("before") or "").strip() or None

    if not user_id:
        logger.error("Missing user_id")
        return {
            "status_code": 400,
            "body": {"status": "error", "message": "user_id is required"},
        }

    store = getattr(context, "store", None)

    lister = (
        getattr(store, "list_conversations", None)
        or getattr(store, "listConversations", None)
    )

    if lister is None or not callable(lister):
        logger.error("context.store.list_conversations is unavailable")
        return {
            "status_code": 501,
            "body": {
                "status": "error",
                "message": "store.list_conversations is unavailable",
                "conversations": [],
            },
        }

    params = {"user_id": user_id, "limit": limit, "order": order}
    if after:
        params["after"] = after
    if before:
        params["before"] = before

    logger.log(f"list_conversations params: user_id=..., limit={limit}, order={order}, has_after={bool(after)}")

    try:
        result = await lister(**params)

        # Normalize raw list
        raw_items = []
        if isinstance(result, list):
            raw_items = result
        elif isinstance(result, dict):
            for key in ("items", "conversations", "data", "results"):
                if isinstance(result.get(key), list):
                    raw_items = result[key]
                    break
        elif hasattr(result, "items") and isinstance(result.items, list):
            raw_items = result.items

        conversations = [c for item in raw_items if (c := _normalize_conversation(item))]

        # --- Title fallback: fetch first user message for untitled conversations ---
        if store and hasattr(store, "get_messages"):
            untitled = [c for c in conversations if c["title"] == "New chat"]
            for conv in untitled:
                try:
                    messages = await store.get_messages(
                        conv["id"], limit=5, order="asc"
                    )
                    for msg in (messages or []):
                        role = getattr(msg, "role", None) if not isinstance(msg, dict) else msg.get("role")
                        if role != "user":
                            continue
                        content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")
                        text = str(content or "").replace("\n", " ").strip()
                        if text:
                            conv["title"] = text if len(text) <= 8 else text[:8] + "..."
                            break
                except Exception as e:
                    logger.error(f"failed to fetch first message for {conv['id']}: {e}")
        # -------------------------------------------------------------------------

        def _pick_cursor(key, *aliases):
            if isinstance(result, dict):
                for k in (key, *aliases):
                    v = result.get(k)
                    if v and isinstance(v, str):
                        return v
            for k in (key, *aliases):
                v = getattr(result, k, None)
                if v and isinstance(v, str):
                    return v
            return None

        next_cursor = _pick_cursor("next_cursor", "nextCursor")
        previous_cursor = _pick_cursor("previous_cursor", "previousCursor", "prev_cursor", "prevCursor")

        logger.log(f"list_conversations: count={len(conversations)}, has_next={bool(next_cursor)}")

        return {
            "conversations": conversations,
            "nextCursor": next_cursor,
            "previousCursor": previous_cursor,
        }

    except Exception as e:
        logger.error(f"failed to list conversations: {e}")
        return {
            "status_code": 500,
            "body": {
                "status": "error",
                "message": str(e),
                "conversations": [],
            },
        }
```

---

### 2.2 新增 `agents/delete-conversation/index.py` — 删除会话

路由：**POST `/delete-conversation`**

```python
"""
Delete-conversation handler — EdgeOne Makers

Route: POST /delete-conversation

Permanently deletes a conversation (messages, metadata, global index).
Uses context.store.delete_conversation(conversation_id=...).
Irreversible.
"""

from typing import Any
from .._logger import create_logger

logger = create_logger("delete-conversation")


async def handler(context: Any):
    body = getattr(context.request, "body", None) or {}
    if not isinstance(body, dict):
        body = {}

    cid = str(body.get("conversation_id") or body.get("conversationId") or "").strip()
    user_id = str(body.get("user_id") or body.get("userId") or "").strip() or None

    logger.log(f"conversation_id={cid}, user_id={user_id or '-'}")

    if not cid:
        return {
            "status_code": 400,
            "body": {"status": "error", "message": "conversation_id is required"},
        }

    store = getattr(context, "store", None)

    deleter = (
        getattr(store, "delete_conversation", None)
        or getattr(store, "deleteConversation", None)
    )

    if deleter is None or not callable(deleter):
        logger.error("context.store.delete_conversation is unavailable")
        return {
            "status_code": 501,
            "body": {
                "status": "error",
                "message": "store.delete_conversation is unavailable",
            },
        }

    try:
        kwargs = {"conversation_id": cid}
        if user_id:
            kwargs["user_id"] = user_id
        await deleter(**kwargs)

        logger.log(f"deleted conversation_id={cid}")
        return {"status": "ok", "conversation_id": cid}

    except Exception as e:
        logger.error(f"failed to delete conversation: {e}")
        return {
            "status_code": 500,
            "body": {
                "status": "error",
                "conversation_id": cid,
                "message": str(e),
            },
        }
```

---

### 2.3 修改 `agents/chat/index.py` — 透传 userId

在 `handler()` 函数中，读取 `body.get("userId") or body.get("user_id")` 并在 `append_message` 调用时传入：

**读取**（紧跟 `bot_msg_id` 读取之后）：
```python
raw_user_id = body.get("userId") or body.get("user_id") or "" if isinstance(body, dict) else ""
user_id = str(raw_user_id).strip() or None
```

**保存用户消息时透传**：
```python
await store_adapter.append_message(
    cid, "user", user_message,
    message_id=user_msg_id,
    user_id=user_id,     # 新增
)
```

**保存 assistant 消息时透传**：
```python
await store_adapter.append_message(
    cid, "assistant", assistant_content,
    message_id=bot_msg_id,
    user_id=user_id,     # 新增
)
```

> `append_message` 如果不支持 `user_id` 参数会 `TypeError`，已有的 try/except 兜底会处理。

---

### 2.4 修改 `agents/clear-history/index.py` — 透传 userId

```python
user_id = str(body.get("user_id") or body.get("userId") or "").strip() or None
```

在 `clear_messages` 调用时加上（如支持）：
```python
kwargs = {"conversation_id": cid}  # or positional — 看现有调用方式
if user_id:
    kwargs["user_id"] = user_id
await store.clear_messages(**kwargs)
```

> 如果 `clear_messages` 只接受位置参数 `cid`，可以保持原样，`user_id` 仅作 log 用。

---

### 2.5 `cloud-functions/history/index.ts`（Python 项目中是 TS）

路径：`cloud-functions/history/index.ts`

加上读取 `user_id` 并透传给 `store.getMessages`：

```ts
function getUserId(body: Record<string, unknown>): string {
  const value = body.user_id ?? body.userId;
  return typeof value === 'string' ? value.trim() : '';
}
```

```ts
const userId = getUserId(body);
// ...
const getArgs: Record<string, unknown> = { conversationId, limit: 100, order: 'asc' };
if (userId) getArgs.userId = userId;
const history = await store.getMessages(getArgs);
```

---

## 三、行为说明

### 用户 ID（eo-uuid）

- 首次进入时，前端从 `localStorage['eo-uuid']` 读取；不存在则 `crypto.randomUUID()` 创建并写入。
- 该 ID 在新建/清空/删除会话时**不变**，只代表当前浏览器/用户。
- 所有涉及 store 的请求都把它作为 `user_id` 传给后端。

### 侧栏乐观更新（"首帧即刷新"）

- 用户发送消息后，**第一个 SSE 帧到达时**（`onRawEvent` 第一次触发），前端立刻把当前会话插入侧栏顶部（新会话）或置顶（已有会话）。
- 流式完成后（`onDone`）再调一次 `/conversations` 做权威对账（纠正服务端返回的 title / 时间等）。

### 乐观删除

- 点击垃圾桶 → `window.confirm` → 立刻从列表移除 / 若是当前活跃会话则创建新空会话 → fire-and-forget 后端 `/delete-conversation`。
- 不等待后端响应，不显示 spinner；后端失败仅打印 `console.warn`。

### 会话列表不显示 loading 遮罩

- 初始请求期间（`conversationsLoading === true` 且列表为空）直接渲染空白，不显示 spinner。
- 数据到达后列表自然出现。

---

## 四、实施顺序建议

1. **先复制前端文件**（types、api、i18n、ConversationSidebar、App.tsx、App.module.css）
2. **新建后端两个 handler**（conversations、delete-conversation）
3. **修改 chat/index.py、clear-history/index.py** 透传 userId
4. **修改 cloud-functions/history/index.ts** 透传 userId
5. `npx tsc --noEmit` 确认 TypeScript 无报错
6. 本地 `npm run dev:agents` 联调验证

---

## 五、不需要改动的文件

- `agents/stop/index.py`
- `agents/chat/_stream.py`（stream state 不涉及 userId）
- `src/components/ChatWindow.tsx`、`ChatBubble.tsx`、`ChatInput.tsx` 等聊天 UI 组件
- `src/lib/imageStore.ts`、`src/lib/chatUiStore.ts`、`src/lib/idb.ts`
- `edgeone.json`、`vite.config.ts`、`tsconfig.json`
