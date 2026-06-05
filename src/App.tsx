import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import type {
  Message,
  ToolLampState,
  ImageAttachment,
  ImageSsePayload,
  ConversationSummary,
} from './types';
import {
  deleteConversation,
  fetchConversationHistory,
  listConversations,
  sendMessageStream,
  stopAgent,
} from './api';
import type { RawSseEvent } from './api';
import { I18nProvider, LangToggle, useT, MessageKeys } from './i18n';
import {
  base64ToBlob,
  saveImage,
  loadConversationImages,
  deleteConversationImages,
  createObjectUrl,
  revokeAllObjectUrls,
  makeStorageKey,
} from './lib/imageStore';
import { saveSnapshot, loadSnapshot, deleteSnapshot } from './lib/chatUiStore';
import ToolIndicators from './components/ToolIndicators';
import ChatWindow from './components/ChatWindow';
import ChatInput from './components/ChatInput';
import CodeViewer from './components/CodeViewer';
import DebugPanel from './components/DebugPanel';
import ConversationSidebar from './components/ConversationSidebar';
import styles from './App.module.css';

const LAMP_IDS = ['commands', 'files', 'code_interpreter', 'browser'] as const;
type LampId = typeof LAMP_IDS[number];
const LAMP_ICONS: Record<string, string> = { commands: '⌨️', files: '📁', code_interpreter: '🐍', browser: '🌐' };

/**
 * Map an EdgeOne platform tool name to a lamp group.
 *
 * The runtime exposes fine-grained tools (e.g. `browser_fetch`,
 * `browser_screenshot`, `files_read`, `commands_run`,
 * `code_interpreter_python`). The header only has 4 lamps, so we collapse
 * each family by prefix / keyword. Returns null for tools that don't belong
 * to any lamp group (e.g. `web_search`, `load_skill`).
 */
function toolToLampId(toolName: string): LampId | null {
  const name = toolName.toLowerCase();
  if (name.startsWith('browser') || name.includes('browse')) return 'browser';
  if (name.startsWith('code_interpreter') || name.startsWith('code-interpreter') || name.startsWith('interpreter')) return 'code_interpreter';
  if (name.startsWith('files') || name.startsWith('file_') || name.startsWith('fs_')) return 'files';
  if (name.startsWith('commands') || name.startsWith('command_') || name.startsWith('cmd_') || name.startsWith('shell') || name === 'exec') return 'commands';
  if ((LAMP_IDS as readonly string[]).includes(name)) return name as LampId;
  return null;
}
const LAMP_I18N_KEYS: Record<string, string> = { commands: 'tool.commands', files: 'tool.files', code_interpreter: 'tool.codeRunner', browser: 'tool.browser' };

const CONVERSATION_ID_STORAGE_KEY = 'eo_conversation_id';
const EO_USER_ID_STORAGE_KEY = 'eo-uuid';
const CONVERSATIONS_PAGE_SIZE = 20;

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

/**
 * Stable user-level identifier persisted in localStorage.
 * All conversations created in this browser are scoped to this UUID,
 * which is sent to the backend as `userId` for filtering and indexing.
 */
function getOrCreateEoUuid(): string {
  const cached = localStorage.getItem(EO_USER_ID_STORAGE_KEY);
  if (cached) return cached;

  const eoUuid = crypto.randomUUID();
  localStorage.setItem(EO_USER_ID_STORAGE_KEY, eoUuid);
  return eoUuid;
}

function isWebSearchToolEvent(event: RawSseEvent): boolean {
  if (event.eventType !== 'tool_called' || !event.data || typeof event.data !== 'object') {
    return false;
  }
  const tool = (event.data as { tool?: unknown }).tool;
  return tool === 'web_search' || tool === 'browser';
}

// Module-level dedup flag — outside React lifecycle, unaffected by StrictMode
let _historyFetchInFlight = false;

export default function App() {
  return (
    <I18nProvider>
      <LangToggle />
      <AppInner />
    </I18nProvider>
  );
}

function AppInner() {
  const { t } = useT();

  const buildLamps = useCallback((): ToolLampState[] => LAMP_IDS.map(id => ({
    id,
    label: t(LAMP_I18N_KEYS[id] as MessageKeys),
    icon: LAMP_ICONS[id],
    active: false,
    animKey: 0,
  })), [t]);

  const [messages, setMessages] = useState<Message[]>([]);
  const [lamps, setLamps]       = useState<ToolLampState[]>(buildLamps);
  const [loading, setLoading]   = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  // Name of the skill currently being loaded by the SDK. null when no skill
  // is in flight. Set by the `skill_loaded` SSE event (singular — fires
  // when the SDK ACTUALLY loads a skill for this turn), auto-cleared
  // after a short interval so the pill animates out.
  const [skillInUse, setSkillInUse] = useState<string | null>(null);
  const [rightPanelMode, setRightPanelMode] = useState<'code' | 'debug'>('code');

  // Conversation list state (left sidebar)
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationsLoading, setConversationsLoading] = useState(true);
  const [conversationsLoadingMore, setConversationsLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | undefined>(undefined);
  const [activeConversationId, setActiveConversationId] = useState<string>(() =>
    getOrCreateConversationId(),
  );

  // Stable user identifier — derived once, never changes for the lifetime of this browser
  const eoUuidRef = useRef<string>(getOrCreateEoUuid());

  // Update lamp labels when language changes
  useEffect(() => {
    setLamps(prev => prev.map(l => ({
      ...l,
      label: t(LAMP_I18N_KEYS[l.id] as MessageKeys),
    })));
  }, [t]);

  const [debugEvents, setDebugEvents] = useState<RawSseEvent[]>([]);

  const botMsgIdRef = useRef<string>('');
  const abortCtrlRef = useRef<AbortController | null>(null);
  const conversationIdRef = useRef<string>(activeConversationId);

  // Keep ref in sync with state — sendMessageStream and other callbacks read from ref
  useEffect(() => {
    conversationIdRef.current = activeConversationId;
  }, [activeConversationId]);

  // Guard: don't overwrite snapshot during initial restore phase.
  // Only start persisting once user has interacted (sent a message).
  const initDoneRef = useRef(false);

  // Persist UI snapshot whenever messages change (debounced)
  const snapshotTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (messages.length === 0) return;
    if (!initDoneRef.current) return; // Skip snapshot save during restore phase

    if (snapshotTimerRef.current) clearTimeout(snapshotTimerRef.current);
    snapshotTimerRef.current = setTimeout(() => {
      saveSnapshot(conversationIdRef.current, messages);
    }, 500);

    return () => {
      if (snapshotTimerRef.current) clearTimeout(snapshotTimerRef.current);
    };
  }, [messages]);

  /**
   * Load a conversation's messages, snapshot and image cache and put them on screen.
   * Used both for the initial restore and for switching to another conversation.
   */
  const loadConversation = useCallback(async (convId: string) => {
    setHistoryLoading(true);
    setMessages([]);
    setDebugEvents([]);
    initDoneRef.current = false;

    revokeAllObjectUrls();

    try {
      const [history, snapshot, storedImages] = await Promise.all([
        fetchConversationHistory(convId, eoUuidRef.current),
        loadSnapshot(convId),
        loadConversationImages(convId),
      ]);

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

      function rebuildImages(images: Message['images']): Message['images'] {
        if (!images || images.length === 0) return images;
        return images.map(img => {
          if (typeof img === 'string') return img;
          const urlInfo = imageUrlMap.get(img.id);
          return urlInfo ? { ...img, url: urlInfo.url, persistent: true } : img;
        });
      }

      let merged: Message[];
      if (snapshot.length > 0) {
        merged = snapshot.map(msg => ({
          ...msg,
          images: rebuildImages(msg.images),
        }));
      } else if (history.length > 0) {
        merged = history;
      } else {
        merged = [];
      }

      setMessages(merged);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  /** Refresh the sidebar conversation list — usually after sending or switching. */
  const refreshConversations = useCallback(async (mode: 'replace' | 'append' = 'replace', cursor?: string) => {
    if (mode === 'append') {
      setConversationsLoadingMore(true);
    } else {
      setConversationsLoading(true);
    }
    try {
      const res = await listConversations({
        userId: eoUuidRef.current,
        limit: CONVERSATIONS_PAGE_SIZE,
        order: 'desc',
        after: cursor,
      });

      setNextCursor(res.nextCursor);

      if (mode === 'append') {
        setConversations(prev => {
          const seen = new Set(prev.map(c => c.id));
          const merged = [...prev];
          for (const c of res.conversations) {
            if (!seen.has(c.id)) merged.push(c);
          }
          return merged;
        });
      } else {
        setConversations(res.conversations);
      }
    } finally {
      if (mode === 'append') {
        setConversationsLoadingMore(false);
      } else {
        setConversationsLoading(false);
      }
    }
  }, []);

  // Initial load: history (only if previously visited) + conversations list
  useEffect(() => {
    void refreshConversations('replace');

    if (!getExistingConversationId() || _historyFetchInFlight) {
      // First visit OR a sibling fetch is in flight — skip history fetch
      if (!getExistingConversationId()) setHistoryLoading(false);
      return;
    }

    _historyFetchInFlight = true;
    loadConversation(conversationIdRef.current).finally(() => {
      _historyFetchInFlight = false;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  /** Clear the assistant message's `streaming` flag (hides the blinking caret). */
  const clearBotStreaming = useCallback(() => {
    setMessages(prev => {
      let changed = false;
      const next = prev.map(m => {
        if (m.id === botMsgIdRef.current && m.streaming) {
          changed = true;
          const { streaming, ...rest } = m;
          return rest;
        }
        return m;
      });
      return changed ? next : prev;
    });
  }, []);

  /** Handle an incoming image SSE event: persist to IndexedDB and append ref to message. */
  const handleImageEvent = useCallback(async (payload: ImageSsePayload) => {
    const { imageId, base64, mimeType = 'image/png', size } = payload;
    const convId = conversationIdRef.current;
    const msgId = botMsgIdRef.current;
    const storageKey = makeStorageKey(convId, imageId);

    const blob = base64ToBlob(base64, mimeType);
    const actualSize = size || blob.size;
    let persistent = false;

    try {
      await saveImage({
        conversationId: convId,
        messageId: msgId,
        imageId,
        blob,
        mimeType,
      });
      persistent = true;
    } catch (e) {
      console.warn('[image] IndexedDB save failed, using temporary URL:', e);
    }

    const url = persistent
      ? createObjectUrl(storageKey, blob)
      : URL.createObjectURL(blob);

    const attachment: ImageAttachment = {
      id: imageId,
      storageKey,
      url,
      mimeType,
      size: actualSize,
      createdAt: Date.now(),
      persistent,
    };

    setMessages(prev =>
      prev.map(m =>
        m.id === msgId
          ? { ...m, images: [...(m.images || []), attachment] }
          : m
      )
    );
  }, []);

  const finishStream = useCallback(() => {
    setLoading(false);
    abortCtrlRef.current = null;
  }, []);

  const handleSend = useCallback(async (text: string) => {
    initDoneRef.current = true;
    setRightPanelMode('debug');

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };

    const botMsgId = crypto.randomUUID();
    botMsgIdRef.current = botMsgId;
    const botMsg: Message = {
      id: botMsgId,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      streaming: true,
    };

    setMessages(prev => [...prev, userMsg, botMsg]);
    setLoading(true);

    /**
     * Optimistic sidebar update — fires as soon as the backend emits its first
     * SSE event (matches ChatGPT's "new chat appears the moment streaming
     * starts" UX). For brand-new conversations we prepend a synthesized summary;
     * for existing ones we just bump them to the top.
     *
     * Server reconciliation still happens in onDone() via refreshConversations,
     * which can correct the title if the runtime later overrides it.
     */
    let sidebarPrimed = false;
    const cleanedText = text.replace(/\s+/g, ' ').trim();
    const optimisticTitle =
      cleanedText.length === 0 ? 'New chat'
        : cleanedText.length <= 8 ? cleanedText
          : `${cleanedText.slice(0, 8)}...`;

    const primeSidebar = () => {
      if (sidebarPrimed) return;
      sidebarPrimed = true;

      const convId = conversationIdRef.current;
      const now = Date.now();

      setConversations(prev => {
        const idx = prev.findIndex(c => c.id === convId);
        if (idx === -1) {
          // Brand-new conversation — prepend.
          const summary: ConversationSummary = {
            id: convId,
            title: optimisticTitle,
            lastMessageAt: now,
            userId: eoUuidRef.current,
          };
          return [summary, ...prev];
        }
        // Existing conversation — bump to top and refresh timestamp.
        const next = [...prev];
        const [moved] = next.splice(idx, 1);
        next.unshift({ ...moved, lastMessageAt: now });
        return next;
      });
    };

    const ctrl = sendMessageStream(text, {
      onTextDelta(delta) {
        finishBotActivity();
        updateBotMessage(content => content + delta);
      },

      onToolCalled(toolName) {
        if (toolName === 'web_search' || toolName === 'browser') {
          setBotActivity({ type: 'web_search', label: 'Web searching...', status: 'active' });
        }

        const lampId = toolToLampId(toolName);
        if (!lampId) return;

        setLamps(prev =>
          prev.map(l =>
            l.id === lampId
              ? { ...l, active: true, animKey: l.animKey + 1 }
              : l
          )
        );
        setTimeout(() => {
          setLamps(prev =>
            prev.map(l => (l.id === lampId ? { ...l, active: false } : l))
          );
        }, 1000);
      },

      onImage(payload) {
        finishBotActivity();
        handleImageEvent(payload);
      },

      onRawEvent(event) {
        // Every backend SSE frame flows through here, so this is the cheapest
        // hook for "first byte from backend" — covers text_delta, tool_called,
        // skills_available, debug_msg, image, etc.
        primeSidebar();

        if (!isWebSearchToolEvent(event)) {
          finishBotActivity();
        }
        // Coalesce consecutive text_delta events into a single growing entry,
        // so a multi-paragraph response doesn't flood the debug panel with
        // hundreds of one-token rows.
        if (event.eventType === 'text_delta') {
          const delta = (event.data as { delta?: string } | null)?.delta ?? '';
          setRightPanelMode('debug');
          setDebugEvents(prev => {
            const last = prev[prev.length - 1];
            if (last && last.eventType === 'text_delta') {
              const prevDelta = (last.data as { delta?: string } | null)?.delta ?? '';
              const merged: RawSseEvent = {
                ...last,
                data: { delta: prevDelta + delta },
                raw: last.raw + delta,
                timestamp: event.timestamp,
              };
              return [...prev.slice(0, -1), merged];
            }
            return [...prev, event];
          });
          return;
        }
        setRightPanelMode('debug');
        setDebugEvents(prev => [...prev, event]);
        // Only react to `skill_loaded` (singular). The plural
        // `skills_available` / `skills_loaded` events fire on every
        // request as catalog/config announcements regardless of whether
        // the model actually uses a skill — they would flash the pill on
        // every chat. The event payload's `name` is the skill's identifier;
        // we surface it directly so the user sees WHICH skill is loading.
        if (event.eventType === 'skill_loaded') {
          const name =
            (event.data as { name?: unknown } | null)?.name;
          if (typeof name === 'string' && name.length > 0) {
            setSkillInUse(name);
            setTimeout(() => setSkillInUse(null), 2000);
          }
        }
      },

      onDone() {
        finishBotActivity();
        clearBotStreaming();
        finishStream();
        // Reconcile with backend so the title (and any other fields the runtime
        // synthesized) reflect the server's authoritative state.
        void refreshConversations('replace');
      },

      onError() {
        finishBotActivity();
        clearBotStreaming();
        updateBotMessage(content => content || t("status.error"));
        finishStream();
      },
    }, conversationIdRef.current, { userMsgId: userMsg.id, botMsgId }, eoUuidRef.current);

    abortCtrlRef.current = ctrl;
  }, [updateBotMessage, setBotActivity, finishBotActivity, clearBotStreaming, handleImageEvent, finishStream, refreshConversations, t]);

  const handleClearHistory = useCallback(() => {
    const oldConvId = conversationIdRef.current;

    // The trash button in ChatInput is the same affordance as the trash
    // icon on a sidebar item: it should DELETE the conversation entirely,
    // not just clear its messages. Using `clearConversationHistory` here
    // would leave the old conversation in the sidebar with an empty body
    // and a fallback "New chat" title — confusing for users who clicked
    // trash expecting "make this thread go away".
    //
    // Optimistically drop from the sidebar so the user sees the row
    // disappear immediately; the network call is fire-and-forget.
    setConversations(prev => prev.filter(c => c.id !== oldConvId));

    deleteConversation(oldConvId, eoUuidRef.current).then(ok => {
      if (!ok) {
        console.warn('[delete-conversation] backend request failed');
      }
    }).finally(() => {
      // Reconcile with backend in case state diverged.
      void refreshConversations('replace');
    });

    // Cleanup IndexedDB images and UI snapshot for old conversation
    revokeAllObjectUrls();
    deleteConversationImages(oldConvId).catch(() => {});
    deleteSnapshot(oldConvId).catch(() => {});

    const newId = crypto.randomUUID();
    localStorage.setItem(CONVERSATION_ID_STORAGE_KEY, newId);
    conversationIdRef.current = newId;
    setActiveConversationId(newId);
    setMessages([]);
    setDebugEvents([]);
    setRightPanelMode('code');
    initDoneRef.current = false;
  }, [refreshConversations]);

  const handleStop = useCallback(() => {
    if (abortCtrlRef.current) {
      abortCtrlRef.current.abort();
      abortCtrlRef.current = null;
    }

    finishBotActivity();
    updateBotMessage(content => content ? content + '\n\n' + t("status.stopped") : t("status.stopped"));
    setLoading(false);

    stopAgent(conversationIdRef.current).then(ok => {
      if (!ok) {
        updateBotMessage(content => content + '\n\n' + t("status.backendError"));
      }
    });
  }, [finishBotActivity, updateBotMessage, t]);

  /** User clicked a conversation in the sidebar. */
  const handleSelectConversation = useCallback((id: string) => {
    if (loading) return; // disabled while streaming
    if (id === conversationIdRef.current) return;

    localStorage.setItem(CONVERSATION_ID_STORAGE_KEY, id);
    conversationIdRef.current = id;
    setActiveConversationId(id);
    setRightPanelMode('code');
    void loadConversation(id);
  }, [loading, loadConversation]);

  /** User clicked "New chat" in the sidebar. */
  const handleCreateConversation = useCallback(() => {
    if (loading) return;

    revokeAllObjectUrls();

    const newId = crypto.randomUUID();
    localStorage.setItem(CONVERSATION_ID_STORAGE_KEY, newId);
    conversationIdRef.current = newId;
    setActiveConversationId(newId);
    setMessages([]);
    setDebugEvents([]);
    setRightPanelMode('code');
    initDoneRef.current = false;
    setHistoryLoading(false);
  }, [loading]);

  const handleLoadMoreConversations = useCallback(() => {
    if (!nextCursor || conversationsLoadingMore) return;
    void refreshConversations('append', nextCursor);
  }, [nextCursor, conversationsLoadingMore, refreshConversations]);

  /**
   * User clicked the trash icon on a sidebar item.
   *
   * Optimistic delete: immediately remove the item from local UI state and
   * fire-and-forget the backend request. We don't await or block the user —
   * if the network call fails, we log it but don't roll back, since reloading
   * the page will reconcile via /conversations anyway.
   */
  const handleDeleteConversation = useCallback((id: string) => {
    if (loading) return;        // never delete mid-stream
    if (!id) return;

    const confirmed = window.confirm(t('sidebar.deleteConfirm'));
    if (!confirmed) return;

    const isActive = id === conversationIdRef.current;

    // 1. Optimistically drop from sidebar.
    setConversations(prev => prev.filter(c => c.id !== id));

    // 2. If it was the active conversation, swap to a fresh empty one
    //    so the chat panel doesn't keep rendering stale messages.
    if (isActive) {
      revokeAllObjectUrls();
      const newId = crypto.randomUUID();
      localStorage.setItem(CONVERSATION_ID_STORAGE_KEY, newId);
      conversationIdRef.current = newId;
      setActiveConversationId(newId);
      setMessages([]);
      setDebugEvents([]);
      setRightPanelMode('code');
      initDoneRef.current = false;
      setHistoryLoading(false);
    }

    // 3. Best-effort cleanup of local caches — user doesn't wait on these.
    void deleteSnapshot(id).catch(() => {});
    void deleteConversationImages(id).catch(() => {});

    // 4. Fire-and-forget backend delete. If it fails the user can refresh.
    void deleteConversation(id, eoUuidRef.current).catch(e => {
      console.warn('[delete-conversation] backend request failed:', e);
    });
  }, [loading, t]);

  const sidebarHasMore = useMemo(() => Boolean(nextCursor), [nextCursor]);

  return (
    <div className={styles.shell}>
      <div className={styles.blob1} />
      <div className={styles.blob2} />

      <div className={styles.stage}>
        <ConversationSidebar
          conversations={conversations}
          activeConversationId={activeConversationId}
          loading={conversationsLoading}
          loadingMore={conversationsLoadingMore}
          hasMore={sidebarHasMore}
          disabled={loading}
          onSelect={handleSelectConversation}
          onCreate={handleCreateConversation}
          onLoadMore={handleLoadMoreConversations}
          onDelete={handleDeleteConversation}
        />

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
            {skillInUse && <span className={styles.skillsLoading}>using {skillInUse}</span>}
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
