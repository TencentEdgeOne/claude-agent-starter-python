/**
 * 后端接口（EdgeOne Pages Functions）
 *
 * 路由映射规则（文件 → 路由）：
 *   agents/chat/index.ts    → POST /chat          主聊天入口
 *   agents/stop/index.ts    → POST /stop          中断正在执行的 agent
 *   agents/history/index.ts → POST /history        获取历史消息
 *
 * 本文件集中定义所有路径 + 请求封装，方便以后扩展子路由。
 */

import type { Message, ImageSsePayload } from './types';

export const API = {
  chat: '/chat',
  chatStop: '/stop',
  history: '/history',
} as const;

export interface StreamCallbacks {
  onTextDelta: (delta: string) => void;
  onToolCalled: (toolName: string) => void;
  onImage: (payload: ImageSsePayload) => void;
  onDone: () => void;
  onError: (err: Error) => void;
}

/** 获取当前 conversation 的历史消息，用于刷新页面后恢复聊天窗口。 */
export async function fetchConversationHistory(conversationId: string): Promise<Message[]> {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(API.history, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'pages-agent-conversation-id': conversationId,
        },
        body: JSON.stringify({}),
      });

      // 409 = 同 conversation 有活跃请求（React StrictMode 双渲染导致），等一下重试
      if (res.status === 409) {
        await new Promise(r => setTimeout(r, 500));
        continue;
      }

      if (!res.ok) return [];

      const data = await res.json().catch(() => null) as { messages?: Message[] } | null;
      return Array.isArray(data?.messages) ? data.messages : [];
    } catch {
      return [];
    }
  }
  return [];
}

/**
 * 通过 SSE 流式调用 POST /chat
 * 后端推送事件：text_delta / tool_called / image / ping / done / error
 *
 * 返回一个 AbortController，调用方可用它中断请求（或配合 /stop 端点优雅中止）。
 */
export function sendMessageStream(
  message: string,
  callbacks: StreamCallbacks,
  conversationId?: string,
  userMsgId?: string,
  botMsgId?: string,
): AbortController {
  const ctrl = new AbortController();

  (async () => {
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (conversationId) {
        headers['pages-agent-conversation-id'] = conversationId;
      }

      const res = await fetch(API.chat, {
        method: 'POST',
        headers,
        body: JSON.stringify({ message, userMsgId, botMsgId }),
        signal: ctrl.signal,
      });

      if (!res.ok) {
        callbacks.onError(new Error(`HTTP ${res.status}: ${await res.text().catch(() => '')}`));
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) {
        callbacks.onError(new Error('ReadableStream not supported'));
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let doneReceived = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE 格式：每个事件以 \n\n 分隔
        const parts = buffer.split('\n\n');
        // 最后一段可能不完整，保留在 buffer 里
        buffer = parts.pop() || '';

        for (const part of parts) {
          if (!part.trim()) continue;
          dispatchSseChunk(part, callbacks, () => { doneReceived = true; });
        }
      }

      // 仅在后端未发送 done 事件时作为 fallback 触发完成
      if (!doneReceived) {
        callbacks.onDone();
      }
    } catch (err) {
      // AbortError 不触发错误回调
      if (err instanceof DOMException && err.name === 'AbortError') return;
      callbacks.onError(err instanceof Error ? err : new Error(String(err)));
    }
  })();

  return ctrl;
}

/** 解析一条 SSE 事件并分发给对应回调 */
function dispatchSseChunk(part: string, cb: StreamCallbacks, markDone: () => void): void {
  let eventType = '';
  let data = '';

  for (const line of part.split('\n')) {
    if (line.startsWith('event: ')) {
      eventType = line.slice(7);
    } else if (line.startsWith('data: ')) {
      data = line.slice(6);
    }
  }

  if (!eventType || !data) return;

  try {
    const parsed = JSON.parse(data);
    switch (eventType) {
      case 'text_delta':
        cb.onTextDelta(parsed.delta);
        break;
      case 'tool_called':
        cb.onToolCalled(parsed.tool);
        break;
      case 'image':
        if (parsed.base64) {
          cb.onImage({
            imageId: parsed.imageId || crypto.randomUUID(),
            base64: parsed.base64,
            mimeType: parsed.mimeType || 'image/png',
            size: parsed.size || 0,
          });
        }
        break;
      case 'error':
        cb.onError(new Error(parsed.message || 'agent returned error'));
        break;
      case 'done':
        markDone();
        cb.onDone();
        break;
    }
  } catch {
    // 忽略解析失败的事件
  }
}

/**
 * 请求后端中断当前正在执行的 agent
 *
 * 注意：stop 请求的 header 不能带和 chat 相同的 conversation_id，
 * 否则 runtime 会用 stop 的 cancel_event 覆盖 chat 的 cancel_event，
 * 导致 abort_active_run 失效。目标 conversation_id 只通过 body 传递。
 */
export async function stopAgent(conversationId?: string): Promise<boolean> {
  try {
    const res = await fetch(API.chatStop, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId }),
    });
    return res.ok;
  } catch {
    return false;
  }
}
