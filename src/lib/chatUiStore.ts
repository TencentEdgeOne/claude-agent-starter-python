/**
 * Local UI history snapshot store (IndexedDB).
 *
 * Stores lightweight Message[] snapshots that preserve image attachment references
 * (but NOT base64 or blob: URLs) so the UI can recover from page refresh.
 */

import type { Message, ImageAttachment } from '../types';

const DB_NAME = 'chat-ui-store-db';
const DB_VERSION = 1;
const STORE_NAME = 'snapshots';

interface SnapshotRecord {
  conversationId: string;
  messages: Message[];
  updatedAt: number;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'conversationId' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/**
 * Sanitize messages before persisting:
 * - Strip runtime `url` field from ImageAttachment
 * - Drop raw base64 strings from images array
 */
function sanitizeForStorage(messages: Message[]): Message[] {
  if (!messages.some(msg => msg.activity || (msg.images && msg.images.length > 0))) {
    return messages;
  }

  return messages.map(msg => {
    const { activity: _activity, ...messageWithoutActivity } = msg;
    if (!msg.images || msg.images.length === 0) return messageWithoutActivity;

    const cleanImages = msg.images
      .filter(img => typeof img !== 'string') // Drop legacy base64 strings
      .map(img => {
        const attachment = img as ImageAttachment;
        // Strip runtime-only url field; will be rebuilt from IndexedDB on refresh
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { url: _url, ...rest } = attachment;
        return { ...rest, url: '' } as ImageAttachment;
      });

    return { ...messageWithoutActivity, images: cleanImages.length > 0 ? cleanImages : undefined };
  });
}

/** Save snapshot (debounced from App.tsx) */
export async function saveSnapshot(conversationId: string, messages: Message[]): Promise<void> {
  const record: SnapshotRecord = {
    conversationId,
    messages: sanitizeForStorage(messages),
    updatedAt: Date.now(),
  };

  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/** Load snapshot messages for a conversation */
export async function loadSnapshot(conversationId: string): Promise<Message[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const req = tx.objectStore(STORE_NAME).get(conversationId);
    req.onsuccess = () => {
      const record = req.result as SnapshotRecord | undefined;
      resolve(record?.messages || []);
    };
    req.onerror = () => reject(req.error);
  });
}

/** Delete snapshot for a conversation */
export async function deleteSnapshot(conversationId: string): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).delete(conversationId);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}
