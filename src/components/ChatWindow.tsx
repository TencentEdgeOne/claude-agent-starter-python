import { useEffect, useRef } from 'react';
import type { Message } from '../types';
import { useT } from '../i18n';
import ChatBubble from './ChatBubble';
import styles from './ChatWindow.module.css';

interface Props {
  messages: Message[];
  loading: boolean;
}

export default function ChatWindow({ messages, loading }: Props) {
  const windowRef = useRef<HTMLDivElement>(null);
  const { t } = useT();

  useEffect(() => {
    // Nothing to scroll to when the window is empty.
    if (messages.length === 0 && !loading) return;
    // Drive scroll on the container's own scrollTop instead of using
    // scrollIntoView — the latter walks every ancestor, which scrolls the
    // page header out of view.
    const el = windowRef.current;
    if (!el) return;
    // While streaming, use 'instant' so successive smooth animations don't
    // pile up and jitter; once streaming ends, fall back to 'smooth'.
    el.scrollTo({ top: el.scrollHeight, behavior: loading ? 'instant' : 'smooth' });
  }, [messages, loading]);

  return (
    <div ref={windowRef} className={styles.window}>
      {messages.length === 0 && (
        <div className={styles.empty}>
          <span className={styles.emptyIcon}>⬡</span>
          <p className={styles.emptyTitle}>{t("empty.title")}</p>
          <p className={styles.emptyHint}>
            {t("empty.hint")}
          </p>
          <p className={styles.emptyFeatures}>
            {t("empty.features")}
          </p>
        </div>
      )}

      {messages.map(msg => (
        <ChatBubble key={msg.id} message={msg} />
      ))}

      {/* The 3-dot typing row only fills the gap "waiting for the first
       * token". Once the assistant bubble has any content (or its own
       * activity sub-indicator takes over), the in-bubble streamingCaret
       * carries the "still working" signal — this avoids two parallel bot
       * bubbles in the same turn. */}
      {loading && !(messages.length > 0 && messages[messages.length - 1].role === 'assistant' && (messages[messages.length - 1].content.length > 0 || messages[messages.length - 1].activity)) && (
        <div className={styles.typingRow}>
          <div className={styles.avatar}>⬡</div>
          <div className={styles.typing}>
            <span />
            <span />
            <span />
          </div>
        </div>
      )}
    </div>
  );
}
