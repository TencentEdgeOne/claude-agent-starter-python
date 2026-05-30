import { useState, useCallback, useEffect, useRef } from 'react';
import type { Message, ToolLampState, ImageAttachment, ImageSsePayload } from './types';
import { clearConversationHistory, fetchConversationHistory, sendMessageStream, stopAgent } from './api';
import type { RawSseEvent } from './api';
import { base64ToBlob, saveImage, makeStorageKey, loadConversationImages, deleteConversationImages, createObjectUrl, revokeAllObjectUrls } from './lib/imageStore';
import { saveSnapshot, loadSnapshot, deleteSnapshot } from './lib/chatUiStore';
import { I18nProvider, LangToggle, useT, MessageKeys } from './i18n';
import ToolIndicators from './components/ToolIndicators';
import ChatWindow from './components/ChatWindow';
import ChatInput from './components/ChatInput';
import CodeViewer from './components/CodeViewer';
import DebugPanel from './components/DebugPanel';
import styles from './App.module.css';

const LAMP_IDS = ['commands', 'files', 'code_interpreter', 'browser'] as const;
const LAMP_ICONS: Record<string, string> = { commands: '⌨️', files: '📁', code_interpreter: '🐍', browser: '🌐' };
const LAMP_I18N_KEYS: Record<string, string> = { commands: 'tool.commands', files: 'tool.files', code_interpreter: 'tool.codeRunner', browser: 'tool.browser' };

const CONVERSATION_ID_STORAGE_KEY = 'eo_conversation_id';

/** Returns existing conversation ID from localStorage, or null if first visit */
function getExistingConversationId(): string | null {
  return localStorage.getItem(CONVERSATION_ID_STORAGE_KEY);
}

/** Returns existing or creates a new conversation ID */
function getOrCreateConversationId(): string {
  const cached = getExistingConversationId();
  if (cached) return cached;

  const conversationId = crypto.randomUUID();
  localStorage.setItem(CONVERSATION_ID_STORAGE_KEY, conversationId);
  return conversationId;
}

function isWebSearchToolEvent(event: RawSseEvent): boolean {
  if (event.eventType !== 'tool_called' || !event.data || typeof event.data !== 'object') {
    return false;
  }
  const tool = (event.data as { tool?: unknown }).tool;
  return tool === 'web_search' || tool === 'browser';
}

function isWebSearchSkillEvent(event: RawSseEvent): boolean {
  if (event.eventType !== 'skill_loaded' || !event.data || typeof event.data !== 'object') {
    return false;
  }
  return (event.data as { name?: unknown }).name === 'web-search';
}

// ✅ 模块级去重标记 —— 脱离 React 生命周期，StrictMode 无法干扰
let _historyFetchInFlight = false;

function AppInner() {
  const { t } = useT();

  const buildLamps = useCallback((): ToolLampState[] =>
    LAMP_IDS.map(id => ({
      id,
      label: t(LAMP_I18N_KEYS[id] as MessageKeys),
      icon: LAMP_ICONS[id],
      active: false,
      animKey: 0,
    })),
    [t]
  );

  const [messages, setMessages] = useState<Message[]>([]);
  const [lamps, setLamps]       = useState<ToolLampState[]>(buildLamps);
  const [loading, setLoading]   = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [debugEvents, setDebugEvents] = useState<RawSseEvent[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [rightPanelMode, setRightPanelMode] = useState<'code' | 'debug'>('code');

  const botMsgIdRef = useRef<string>('');
  const abortCtrlRef = useRef<AbortController | null>(null);
  const hadExistingConversationIdRef = useRef(getExistingConversationId() !== null);
  const conversationIdRef = useRef<string>(getOrCreateConversationId());
  const initDoneRef = useRef(false);       // Guards snapshot saving during recovery
  const snapshotTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Update lamp labels when language changes
  useEffect(() => {
    setLamps(prev =>
      prev.map(l => ({
        ...l,
        label: t(LAMP_I18N_KEYS[l.id] as MessageKeys),
      }))
    );
  }, [t]);

  // === History Recovery (on mount) ===
  useEffect(() => {
    // First visit: no existing conversation → skip history fetch for instant load
    if (!hadExistingConversationIdRef.current) {
      setHistoryLoading(false);
      return;
    }

    const convId = conversationIdRef.current;
    let restoredFromSnapshot = false;

    const restoreSnapshot = () => Promise.all([
      loadSnapshot(convId).catch(() => [] as Message[]),
      loadConversationImages(convId).catch(() => []),
    ]).then(([snapshot, storedImages]) => {
      // Build imageId → URL map from IndexedDB blobs
      const imageUrlMap = new Map<string, { url: string; mimeType: string; size: number; storageKey: string }>();
      for (const record of storedImages) {
        const url = createObjectUrl(record.storageKey, record.blob);
        imageUrlMap.set(record.imageId, {
          url,
          mimeType: record.mimeType,
          size: record.size,
          storageKey: record.storageKey,
        });
      }

      // Rebuild images: restore blob: URLs from IndexedDB
      function rebuildImages(images?: (ImageAttachment | string)[]): (ImageAttachment | string)[] | undefined {
        if (!images || images.length === 0) return undefined;
        const rebuilt = images
          .map(img => {
            if (typeof img === 'string') return img; // Legacy base64
            const urlInfo = imageUrlMap.get(img.id);
            if (urlInfo) {
              return { ...img, url: urlInfo.url, persistent: true } as ImageAttachment;
            }
            return img;
          })
          .filter(img => typeof img === 'string' || (img as ImageAttachment).url);
        return rebuilt.length > 0 ? rebuilt : undefined;
      }

      if (snapshot.length > 0) {
        // Snapshot is the authoritative UI source (contains image references)
        restoredFromSnapshot = true;
        const merged = snapshot.map(msg => ({
          ...msg,
          images: rebuildImages(msg.images as (ImageAttachment | string)[] | undefined),
        }));
        setMessages(merged);
        setHistoryLoading(false);
      }
    }).catch(() => {});

    // Deduplicate the backend /history call in React StrictMode, but still let
    // the remounted tree restore local IndexedDB snapshot immediately.
    if (_historyFetchInFlight) {
      restoreSnapshot().finally(() => setHistoryLoading(false));
      return;
    }
    _historyFetchInFlight = true;

    restoreSnapshot().finally(() => {
      fetchConversationHistory(convId).then(history => {
        if (restoredFromSnapshot || history.length === 0) return;
        // Fallback to backend history (text-only, no images)
        setMessages(history);
        saveSnapshot(convId, history).catch(() => {});
      }).finally(() => {
        _historyFetchInFlight = false;
        setHistoryLoading(false);
      });
    });
  }, []);

  // === Debounced Snapshot Saving ===
  useEffect(() => {
    if (messages.length === 0) return;
    if (!initDoneRef.current) return; // Don't save during recovery phase

    if (snapshotTimerRef.current) clearTimeout(snapshotTimerRef.current);
    snapshotTimerRef.current = setTimeout(() => {
      saveSnapshot(conversationIdRef.current, messages).catch(err => {
        console.warn('[chatUiStore] snapshot save failed:', err);
      });
    }, 500);

    return () => {
      if (snapshotTimerRef.current) clearTimeout(snapshotTimerRef.current);
    };
  }, [messages]);

  /** Update the current bot message's content via an updater function. */
  const updateBotMessage = useCallback((updater: (content: string) => string) => {
    setMessages(prev =>
      prev.map(m =>
        m.id === botMsgIdRef.current
          ? { ...m, content: updater(m.content) }
          : m
      )
    );
  }, []);

  const setBotActivity = useCallback((activity: Message['activity']) => {
    setMessages(prev =>
      prev.map(m =>
        m.id === botMsgIdRef.current
          ? { ...m, activity }
          : m
      )
    );
  }, []);

  const finishBotActivity = useCallback(() => {
    setMessages(prev => {
      let changed = false;
      const next = prev.map(m => {
        if (m.id === botMsgIdRef.current && m.activity?.status === 'active') {
          changed = true;
          return { ...m, activity: { ...m.activity, status: 'done' as const } };
        }
        return m;
      });
      return changed ? next : prev;
    });
  }, []);

  const finishStream = useCallback(() => {
    setLoading(false);
    abortCtrlRef.current = null;
  }, []);

  /** Handle incoming image from SSE */
  const handleImageEvent = useCallback(async (payload: ImageSsePayload) => {
    const { imageId, base64, mimeType = 'image/png' } = payload;
    const convId = conversationIdRef.current;
    const msgId = botMsgIdRef.current;
    const storageKey = makeStorageKey(convId, imageId);

    // Decode base64 to Blob
    const blob = base64ToBlob(base64, mimeType);

    let persistent = false;
    try {
      // Persist to IndexedDB
      await saveImage({
        conversationId: convId,
        messageId: msgId,
        imageId,
        blob,
        mimeType,
      });
      persistent = true;
    } catch (e) {
      console.warn('[imageStore] IndexedDB save failed, using temporary URL:', e);
    }

    // Create blob: URL for rendering
    const url = persistent
      ? createObjectUrl(storageKey, blob)
      : URL.createObjectURL(blob);

    const attachment: ImageAttachment = {
      id: imageId,
      storageKey,
      url,
      mimeType,
      size: blob.size,
      createdAt: Date.now(),
      persistent,
    };

    // Append image to current bot message
    setMessages(prev =>
      prev.map(m =>
        m.id === msgId
          ? { ...m, images: [...(m.images || []), attachment] }
          : m
      )
    );
  }, []);

  const handleSend = useCallback(async (text: string) => {
    // Unlock snapshot saving on first user interaction
    initDoneRef.current = true;
    // Switch right panel to debug mode
    setRightPanelMode('debug');

    const userMsgId = crypto.randomUUID();
    const botMsgId = crypto.randomUUID();
    botMsgIdRef.current = botMsgId;

    const userMsg: Message = {
      id: userMsgId,
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };

    const botMsg: Message = {
      id: botMsgId,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
    };

    setMessages(prev => [...prev, userMsg, botMsg]);
    setLoading(true);

    const ctrl = sendMessageStream(text, {
      onTextDelta(delta) {
        finishBotActivity();
        updateBotMessage(content => content + delta);
      },

      onToolCalled(toolName) {
        if (toolName === 'web_search' || toolName === 'browser') {
          setBotActivity({ type: 'web_search', label: 'Web searching...', status: 'active' });
        }

        setLamps(prev =>
          prev.map(l =>
            l.id === toolName
              ? { ...l, active: true, animKey: l.animKey + 1 }
              : l
          )
        );
        setTimeout(() => {
          setLamps(prev =>
            prev.map(l => (l.id === toolName ? { ...l, active: false } : l))
          );
        }, 1000);
      },

      onImage(payload) {
        finishBotActivity();
        handleImageEvent(payload);
      },

      onRawEvent(event) {
        if (isWebSearchSkillEvent(event)) {
          setBotActivity({ type: 'web_search', label: 'Web searching...', status: 'active' });
        } else if (!isWebSearchToolEvent(event)) {
          finishBotActivity();
        }
        if (event.eventType === 'text_delta') return;
        setRightPanelMode('debug');
        setDebugEvents(prev => [...prev, event]);

        // Show loading indicator briefly while project skills are announced/loaded.
        if (event.eventType === 'skills_available' || event.eventType === 'skill_loaded') {
          setSkillsLoading(true);
          setTimeout(() => setSkillsLoading(false), 2000);
        }
      },

      onDone() {
        finishBotActivity();
        finishStream();
      },

      onError() {
        finishBotActivity();
        updateBotMessage(content => content || t("status.error"));
        finishStream();
      },
    }, conversationIdRef.current, userMsgId, botMsgId);

    abortCtrlRef.current = ctrl;
  }, [updateBotMessage, setBotActivity, finishBotActivity, finishStream, handleImageEvent, t]);

  const handleClearHistory = useCallback(async () => {
    const oldConvId = conversationIdRef.current;

    // Clear backend history for the old conversation without blocking local UI reset.
    clearConversationHistory(oldConvId).then(ok => {
      if (!ok) {
        console.warn('[history] backend clear request failed');
      }
    });

    // Clean up all image-related state
    revokeAllObjectUrls();
    await deleteConversationImages(oldConvId).catch(() => {});
    await deleteSnapshot(oldConvId).catch(() => {});

    // Reset debug panel and right panel mode
    setDebugEvents([]);
    setRightPanelMode('code');
    setSkillsLoading(false);

    localStorage.removeItem(CONVERSATION_ID_STORAGE_KEY);
    const newId = crypto.randomUUID();
    localStorage.setItem(CONVERSATION_ID_STORAGE_KEY, newId);
    conversationIdRef.current = newId;
    setMessages([]);
    initDoneRef.current = false;
  }, []);

  const handleStop = useCallback(() => {
    // 1. 立即中断前端 SSE 读取
    if (abortCtrlRef.current) {
      abortCtrlRef.current.abort();
      abortCtrlRef.current = null;
    }

    // 2. 前端立即显示已中断（乐观 UI，不等后端）
    finishBotActivity();
    updateBotMessage(content => content ? content + '\n\n' + t("status.stopped") : t("status.stopped"));
    setLoading(false);

    // 3. 后端异步执行中断，失败时提示用户
    stopAgent(conversationIdRef.current).then(ok => {
      if (!ok) {
        updateBotMessage(content => content + '\n\n' + t("status.backendError"));
      }
    });
  }, [finishBotActivity, updateBotMessage, t]);

  return (
    <div className={styles.shell}>
      <div className={styles.blob1} />
      <div className={styles.blob2} />

      <div className={styles.stage}>
        <div className={styles.chatPanel}>
          <header className={styles.header}>
            <div className={styles.headerLeft}>
              <span className={styles.logo}>⬡</span>
              <div>
                <p className={styles.title}>{t("app.title")}</p>
                <p className={styles.subtitle}>{t("app.subtitle")}</p>
              </div>
            </div>
            <ToolIndicators lamps={lamps} />
            {skillsLoading && <span className={styles.skillsLoading}>skills loading...</span>}
          </header>

          <div className={styles.chatWindowShell}>
            <ChatWindow messages={messages} loading={loading} />
            {historyLoading && messages.length === 0 && (
              <div className={styles.historyOverlay}>
                <div className={styles.historySpinner} />
              </div>
            )}
          </div>
          <ChatInput onSend={handleSend} onStop={handleStop} onClear={handleClearHistory} disabled={loading} />
        </div>

        <div className={styles.codePanel}>
          {rightPanelMode === 'code' ? (
            <CodeViewer />
          ) : (
            <DebugPanel events={debugEvents} onClear={() => setDebugEvents([])} />
          )}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <I18nProvider>
      <LangToggle />
      <AppInner />
    </I18nProvider>
  );
}
