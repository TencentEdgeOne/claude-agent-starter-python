/**
 * Backend API client (EdgeOne Makers).
 *
 * Route mapping (file → route):
 *   agents/chat/index.py                → POST /chat                main chat entry
 *   agents/stop/index.py                → POST /stop                abort the running agent
 *   agents/history/index.py             → POST /history             load message history
 *   agents/clear-history/index.py       → POST /clear-history       clear message history
 *   agents/conversations/index.py       → POST /conversations       list user conversations
 *   agents/delete-conversation/index.py → POST /delete-conversation permanently delete a conversation
 *
 * This file centralises all paths and request wrappers so adding sub-routes later is straightforward.
 */

import type { Message, ImageSsePayload, ListConversationsParams, ListConversationsResponse } from './types';

export const API = {
  chat: '/chat',
  chatStop: '/stop',
  history: '/history',
  clearHistory: '/clear-history',
  conversations: '/conversations',
  deleteConversation: '/delete-conversation',
} as const;

export interface RawSseEvent {
  eventType: string;
  data: unknown;
  raw: string;
  timestamp: number;
}

export interface SkillInfo {
  name: string;
  label?: string;
  description?: string;
}

export interface SkillLoadedPayload {
  name: string;
  status: 'loaded';
}

export interface StreamCallbacks {
  onTextDelta: (delta: string) => void;
  onToolCalled: (toolName: string) => void;
  onImage: (payload: ImageSsePayload) => void;
  onSkillAvailable?: (skills: SkillInfo[]) => void;
  onSkillLoaded?: (payload: SkillLoadedPayload) => void;
  onDone: () => void;
  onError: (err: Error) => void;
  onRawEvent?: (event: RawSseEvent) => void;
}

/** Fetch the conversation's message history — used to restore the chat window after a page refresh. */
export async function fetchConversationHistory(conversationId: string, userId?: string): Promise<Message[]> {
  const startTime = performance.now();
  console.log(`[history] start: ${new Date().toISOString()}`);

  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const res = await fetch(API.history, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ conversation_id: conversationId, user_id: userId }),
      });

      // 409 = an active request already exists for this conversation (often
      // caused by React StrictMode's double render). Briefly back off and retry.
      if (res.status === 409) {
        await new Promise(r => setTimeout(r, 500));
        continue;
      }

      if (!res.ok) {
        console.log(`[history] end: ${new Date().toISOString()}, total: ${(performance.now() - startTime).toFixed(2)}ms`);
        return [];
      }

      const data = await res.json().catch(() => null) as { messages?: Message[] } | null;
      const messages = Array.isArray(data?.messages) ? data.messages : [];

      console.log(`[history] end: ${new Date().toISOString()}, total: ${(performance.now() - startTime).toFixed(2)}ms`);
      return messages;
    } catch {
      console.log(`[history] end: ${new Date().toISOString()}, total: ${(performance.now() - startTime).toFixed(2)}ms`);
      return [];
    }
  }

  console.log(`[history] end: ${new Date().toISOString()}, total: ${(performance.now() - startTime).toFixed(2)}ms`);
  return [];
}

/**
 * Stream POST /chat over SSE.
 * Backend events: text_delta / tool_called / image / skills_loaded / skills_available / skill_loaded / ping / done / error.
 *
 * Returns an AbortController the caller can use to abort the request (or pair with /stop for a graceful stop).
 */
export function sendMessageStream(
  message: string,
  callbacks: StreamCallbacks,
  conversationId?: string,
  messageIds?: { userMsgId: string; botMsgId: string },
  userId?: string,
): AbortController {
  const ctrl = new AbortController();

  (async () => {
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };
      if (conversationId) {
        headers['makers-conversation-id'] = conversationId;
      }

      const res = await fetch(API.chat, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          message,
          userMsgId: messageIds?.userMsgId,
          botMsgId: messageIds?.botMsgId,
          userId,
        }),
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

        // SSE format: events are separated by \n\n.
        const parts = buffer.split('\n\n');
        // The trailing chunk may be incomplete — keep it in the buffer.
        buffer = parts.pop() || '';

        for (const part of parts) {
          if (!part.trim()) continue;
          dispatchSseChunk(part, callbacks, () => { doneReceived = true; });
        }
      }

      // Fallback: only fire onDone if the backend never sent a `done` event.
      if (!doneReceived) {
        callbacks.onDone();
      }
    } catch (err) {
      // AbortError shouldn't trigger the error callback.
      if (err instanceof DOMException && err.name === 'AbortError') return;
      callbacks.onError(err instanceof Error ? err : new Error(String(err)));
    }
  })();

  return ctrl;
}

/** Parse a single SSE event and dispatch it to the matching callback. */
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

    // Push raw event to debug panel
    if (cb.onRawEvent) {
      cb.onRawEvent({
        eventType,
        data: parsed,
        raw: data,
        timestamp: Date.now(),
      });
    }

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
      case 'skills_available':
        cb.onSkillAvailable?.(parsed.skills || []);
        break;
      case 'skill_loaded':
        cb.onSkillLoaded?.({ name: parsed.name, status: 'loaded' });
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
    // Push raw event even on parse failure
    if (cb.onRawEvent) {
      cb.onRawEvent({
        eventType,
        data: null,
        raw: data,
        timestamp: Date.now(),
      });
    }
  }
}

/**
 * Ask the backend to abort the agent currently running for this conversation.
 *
 * Historical note: an earlier runtime version had a bug where the chat and
 * stop requests shared a single cancel_event slot keyed by header
 * conversation_id, so passing Markers-Conversation-Id on /stop would
 * overwrite the chat's abort signal. The current runtime is expected to
 * route stop independently — but if you ever observe "stop returned 200 yet
 * chat keeps streaming," revisit this and switch to a body-only channel.
 */
export async function stopAgent(conversationId?: string): Promise<boolean> {
  try {
    /**
     * EdgeOne agents/ runtime requires Markers-Conversation-Id on every
     * agents/* request (since 2026-06-05 platform upgrade) — without it
     * the runtime returns 400 (`AGENT_CONVERSATION_ID_REQUIRED`) before
     * the handler runs.
     *
     * Earlier comments in this codebase warned that adding the header on
     * /stop would overwrite chat's abort signal slot. The new runtime is
     * expected to no longer have that bug; if you observe stop succeeding
     * but chat not actually aborting, revisit this and use a different
     * cancellation channel.
     */
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (conversationId) {
      headers['makers-conversation-id'] = conversationId;
    }
    const res = await fetch(API.chatStop, {
      method: 'POST',
      headers,
      body: JSON.stringify({ conversation_id: conversationId }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** Clear the backend conversation history. */
export async function clearConversationHistory(conversationId?: string, userId?: string): Promise<boolean> {
  if (!conversationId) return false;

  try {
    const res = await fetch(API.clearHistory, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId, user_id: userId }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * List conversations for the given user (eo-uuid).
 * Returns at most `limit` (default 20) conversations ordered by lastMessageAt desc by default.
 * Pass `after` from a previous response's `nextCursor` to paginate.
 */
export async function listConversations(params: ListConversationsParams): Promise<ListConversationsResponse> {
  const startTime = performance.now();
  console.log(`[conversations] start: ${new Date().toISOString()}`);

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

    if (!res.ok) {
      console.warn(`[conversations] HTTP ${res.status}`);
      console.log(`[conversations] end: ${new Date().toISOString()}, total: ${(performance.now() - startTime).toFixed(2)}ms`);
      return empty;
    }

    const data = await res.json().catch(() => null) as ListConversationsResponse | null;
    console.log(`[conversations] end: ${new Date().toISOString()}, total: ${(performance.now() - startTime).toFixed(2)}ms, count=${data?.conversations?.length ?? 0}`);
    if (!data || !Array.isArray(data.conversations)) return empty;
    return {
      conversations: data.conversations,
      nextCursor: data.nextCursor,
      previousCursor: data.previousCursor,
    };
  } catch (e) {
    console.warn('[conversations] request failed:', e);
    return empty;
  }
}

/**
 * Permanently delete a conversation (messages + metadata + index).
 * Irreversible — caller must already have confirmed with the user.
 */
export async function deleteConversation(conversationId: string, userId?: string): Promise<boolean> {
  if (!conversationId) return false;

  try {
    const res = await fetch(API.deleteConversation, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: conversationId, user_id: userId }),
    });
    return res.ok;
  } catch (e) {
    console.warn('[delete-conversation] request failed:', e);
    return false;
  }
}
