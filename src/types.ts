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
}

export interface ToolLampState {
  id: string;
  label: string;
  icon: string;
  active: boolean;
  animKey: number;   // 每次点亮时递增，让动画元素重新挂载以复播动画
}
