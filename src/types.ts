export interface ImageAttachment {
  id: string;              // 图片 ID，来自 SSE imageId
  storageKey: string;      // IndexedDB key: `${conversationId}/${imageId}`
  url: string;             // 运行时 blob: URL，只用于渲染，不持久化
  mimeType: string;
  size: number;
  createdAt: number;
  persistent: boolean;     // 是否已成功写入 IndexedDB
}

export interface ImageSsePayload {
  imageId: string;
  base64: string;
  mimeType?: string;
  size?: number;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  images?: (ImageAttachment | string)[];
  activity?: {
    type: 'web_search';
    label: string;
    status: 'active' | 'done';
  };
  /**
   * True while the assistant is actively producing this message
   * (between the first text_delta and the final done/error event).
   * Drives the in-bubble blinking caret to give the user feedback
   * that more content is still streaming. Cleared once done/error fires.
   */
  streaming?: boolean;
}

export interface ToolLampState {
  id: string;
  label: string;
  icon: string;
  active: boolean;
  animKey: number;   // 每次点亮时递增，让动画元素重新挂载以复播动画
}

/**
 * Lightweight summary of a conversation, returned by /conversations.
 * Used to render the left sidebar — does NOT contain full message content.
 */
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
