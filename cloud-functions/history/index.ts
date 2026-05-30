/**
 * History handler — EdgeOne Makers
 * =========================================
 *
 * File path cloud-functions/history/index.ts maps to **POST /history**
 *
 * Reads conversation history from context.store.getMessages() and returns
 * it to the frontend for restoring the chat window after a page refresh.
 *
 * Note: base64Image content is redacted from history responses to avoid
 * sending large payloads to the frontend. Images are restored from
 * client-side IndexedDB instead.
 */

import { createLogger } from '../_logger';
import { redactBase64InText } from '../_redact';

const logger = createLogger('history');

const JSON_HEADERS = { 'Content-Type': 'application/json; charset=UTF-8' } as const;

type FrontendMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
};

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

async function readRequestBody(context: any): Promise<Record<string, unknown>> {
  const body = context.request?.body;
  if (body instanceof Uint8Array) {
    try {
      return JSON.parse(new TextDecoder().decode(body)) as Record<string, unknown>;
    } catch {
      return {};
    }
  }

  if (body && typeof body === 'object' && !Array.isArray(body)) {
    return body as Record<string, unknown>;
  }

  if (typeof body === 'string') {
    try {
      return JSON.parse(body) as Record<string, unknown>;
    } catch {
      return {};
    }
  }

  if (typeof context.request?.json === 'function') {
    try {
      return await context.request.json();
    } catch {
      return {};
    }
  }

  return {};
}

function getConversationId(body: Record<string, unknown>): string {
  const value = body.conversation_id ?? body.conversationId;
  return typeof value === 'string' ? value : '';
}

function contentToText(content: unknown): string {
  if (typeof content === 'string') return redactBase64InText(content);

  if (content !== null && typeof content === 'object' && !Array.isArray(content)) {
    const obj = content as Record<string, unknown>;
    if ('content' in obj) return contentToText(obj.content);
    if ('output' in obj) return contentToText(obj.output);
    if ('text' in obj) return redactBase64InText(String(obj.text ?? ''));
    return '';
  }

  if (Array.isArray(content)) {
    return content
      .filter((item): item is Record<string, unknown> =>
        item !== null && typeof item === 'object',
      )
      .map(item => {
        const text = String(item.text ?? item.output_text ?? '');
        return redactBase64InText(text);
      })
      .filter(Boolean)
      .join('\n');
  }

  return String(content);
}

export async function onRequest(context: any) {
  const startTime = Date.now();
  logger.log(`[history] start: ${new Date(startTime).toISOString()}`);

  const body = await readRequestBody(context);
  const conversationId = getConversationId(body);
  const store = context.store ?? null;

  logger.log('conversationId:', conversationId);

  if (!store || !conversationId) {
    logger.log(`[history] end: ${new Date().toISOString()}, total: ${Date.now() - startTime}ms`);
    return jsonResponse({ conversation_id: conversationId, messages: [] });
  }

  try {
    const history = await store.getMessages({
      conversationId,
      limit: 100,
      order: 'asc',
    });

    const messages: FrontendMessage[] = [];
    for (const item of history) {
      const role = item.role;
      if (role !== 'user' && role !== 'assistant') continue;

      const content = contentToText(item.content);
      if (!content && role === 'user') continue;

      messages.push({
        id: item.messageId ?? `${role}-${item.createdAt ?? 0}`,
        role,
        content: content || '',
        timestamp: item.createdAt ?? 0,
      });
    }

    logger.log(`[history] end: ${new Date().toISOString()}, total: ${Date.now() - startTime}ms`);
    return jsonResponse({ conversation_id: conversationId, messages });
  } catch (e) {
    logger.error('failed to get messages:', e);
    logger.log(`[history] end: ${new Date().toISOString()}, total: ${Date.now() - startTime}ms`);
    return jsonResponse({ conversation_id: conversationId, messages: [] });
  }
}
