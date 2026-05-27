/**
 * IndexedDB image blob storage for tool screenshots.
 *
 * Images are stored as Blobs (binary), keyed by `${conversationId}/${imageId}`.
 * blob: URLs are runtime-only and must be recreated after page refresh.
 */

const DB_NAME = 'tool-images-db';
const DB_VERSION = 1;
const STORE_NAME = 'images';

export interface StoredImageRecord {
  storageKey: string;       // `${conversationId}/${imageId}`
  conversationId: string;
  messageId: string;
  imageId: string;
  blob: Blob;
  mimeType: string;
  size: number;
  createdAt: number;
}

// Runtime cache: storageKey → blob: URL
const activeUrls = new Map<string, string>();

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'storageKey' });
        store.createIndex('byConversation', 'conversationId', { unique: false });
        store.createIndex('byMessage', ['conversationId', 'messageId'], { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/** Decode base64 string to Blob */
export function base64ToBlob(base64: string, mimeType: string = 'image/png'): Blob {
  const byteChars = atob(base64);
  const byteNumbers = new Uint8Array(byteChars.length);
  for (let i = 0; i < byteChars.length; i++) {
    byteNumbers[i] = byteChars.charCodeAt(i);
  }
  return new Blob([byteNumbers], { type: mimeType });
}

/** Generate stable IndexedDB key */
export function makeStorageKey(conversationId: string, imageId: string): string {
  return `${conversationId}/${imageId}`;
}

/** Save image blob to IndexedDB */
export async function saveImage(params: {
  conversationId: string;
  messageId: string;
  imageId: string;
  blob: Blob;
  mimeType: string;
}): Promise<void> {
  const { conversationId, messageId, imageId, blob, mimeType } = params;
  const storageKey = makeStorageKey(conversationId, imageId);
  const record: StoredImageRecord = {
    storageKey,
    conversationId,
    messageId,
    imageId,
    blob,
    mimeType,
    size: blob.size,
    createdAt: Date.now(),
  };

  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/** Load all images for a conversation (used on page refresh) */
export async function loadConversationImages(conversationId: string): Promise<StoredImageRecord[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const index = tx.objectStore(STORE_NAME).index('byConversation');
    const req = index.getAll(conversationId);
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

/** Delete all images for a conversation */
export async function deleteConversationImages(conversationId: string): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const index = store.index('byConversation');
    const req = index.openCursor(conversationId);
    req.onsuccess = () => {
      const cursor = req.result;
      if (cursor) {
        cursor.delete();
        cursor.continue();
      }
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/** Create or reuse a blob: URL for a stored image */
export function createObjectUrl(storageKey: string, blob: Blob): string {
  const existing = activeUrls.get(storageKey);
  if (existing) return existing;

  const url = URL.createObjectURL(blob);
  activeUrls.set(storageKey, url);
  return url;
}

/** Revoke all cached blob: URLs (call on history clear) */
export function revokeAllObjectUrls(): void {
  for (const url of activeUrls.values()) {
    URL.revokeObjectURL(url);
  }
  activeUrls.clear();
}
