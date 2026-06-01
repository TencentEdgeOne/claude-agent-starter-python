import { MouseEvent, useMemo } from 'react';
import type { ConversationSummary } from '../types';
import { useT } from '../i18n';
import styles from './ConversationSidebar.module.css';

interface Props {
  conversations: ConversationSummary[];
  activeConversationId: string;
  loading: boolean;
  loadingMore: boolean;
  hasMore: boolean;
  disabled: boolean;       // Disabled while a stream is running
  onSelect: (id: string) => void;
  onCreate: () => void;
  onLoadMore: () => void;
  onDelete: (id: string) => void;
}

function formatTimestamp(ts: number | undefined, lang: string): string {
  if (!ts || !Number.isFinite(ts)) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '';
  const now = Date.now();
  const diff = now - ts;

  // < 1 minute
  if (diff < 60_000) {
    return lang === 'zh' ? '刚刚' : 'Just now';
  }
  // < 1 hour → "12m"
  if (diff < 60 * 60_000) {
    const m = Math.floor(diff / 60_000);
    return lang === 'zh' ? `${m} 分钟前` : `${m}m ago`;
  }
  // Same day → "14:32"
  const today = new Date();
  if (
    d.getFullYear() === today.getFullYear() &&
    d.getMonth() === today.getMonth() &&
    d.getDate() === today.getDate()
  ) {
    return d.toLocaleTimeString(lang === 'zh' ? 'zh-CN' : 'en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  }
  // Same year → "Mar 12"
  if (d.getFullYear() === today.getFullYear()) {
    return d.toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-US', {
      month: 'short',
      day: 'numeric',
    });
  }
  // Else → "2024-03-12"
  return d.toLocaleDateString(lang === 'zh' ? 'zh-CN' : 'en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}

export default function ConversationSidebar({
  conversations,
  activeConversationId,
  loading,
  loadingMore,
  hasMore,
  disabled,
  onSelect,
  onCreate,
  onLoadMore,
  onDelete,
}: Props) {
  const { t, lang } = useT();

  const items = useMemo(
    () => conversations.map(c => ({
      ...c,
      timeText: formatTimestamp(c.lastMessageAt ?? c.createdAt, lang),
    })),
    [conversations, lang],
  );

  const handleDeleteClick = (event: MouseEvent<HTMLButtonElement>, id: string) => {
    event.stopPropagation();
    event.preventDefault();
    if (disabled) return;
    onDelete(id);
  };

  return (
    <aside className={styles.sidebar} aria-label={t('sidebar.label')}>
      <div className={styles.head}>
        <span className={styles.brand}>
          <span className={styles.brandDot}>⬡</span>
          {t('sidebar.title')}
        </span>
        <button
          type="button"
          className={styles.newBtn}
          onClick={onCreate}
          disabled={disabled}
          aria-label={t('sidebar.newChat')}
          title={t('sidebar.newChat')}
        >
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
          <span>{t('sidebar.newChat')}</span>
        </button>
      </div>

      <div className={styles.listShell}>
        {items.length === 0 ? (
          loading ? (
            // No loading overlay — keep the panel quiet while the first page
            // is fetched. The list will populate the moment data arrives.
            null
          ) : (
            <div className={styles.empty}>
              <p className={styles.emptyTitle}>{t('sidebar.emptyTitle')}</p>
              <p className={styles.emptyHint}>{t('sidebar.emptyHint')}</p>
            </div>
          )
        ) : (
          <ul className={styles.list}>
            {items.map(c => {
              const isActive = c.id === activeConversationId;
              return (
                <li
                  key={c.id}
                  className={`${styles.row} ${isActive ? styles.rowActive : ''}`}
                >
                  <button
                    type="button"
                    className={`${styles.item} ${isActive ? styles.itemActive : ''}`}
                    onClick={() => !disabled && !isActive && onSelect(c.id)}
                    disabled={disabled && !isActive}
                    aria-current={isActive ? 'true' : 'false'}
                  >
                    <div className={styles.itemRow}>
                      <span className={styles.itemTitle}>{c.title}</span>
                      {c.timeText && <span className={styles.itemTime}>{c.timeText}</span>}
                    </div>
                    {c.preview && (
                      <p className={styles.itemPreview}>{c.preview}</p>
                    )}
                  </button>

                  <button
                    type="button"
                    className={styles.deleteBtn}
                    onClick={e => handleDeleteClick(e, c.id)}
                    disabled={disabled}
                    aria-label={t('sidebar.delete')}
                    title={t('sidebar.delete')}
                  >
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                      <path d="M10 11v6" />
                      <path d="M14 11v6" />
                      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                    </svg>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {hasMore && items.length > 0 && (
        <div className={styles.foot}>
          <button
            type="button"
            className={styles.loadMore}
            onClick={onLoadMore}
            disabled={loadingMore || disabled}
          >
            {loadingMore ? t('sidebar.loadingMore') : t('sidebar.loadMore')}
          </button>
        </div>
      )}
    </aside>
  );
}
