import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Message, ImageAttachment } from '../types';
import { useT } from '../i18n';
import styles from './ChatBubble.module.css';

interface Props {
  message: Message;
}

const TABLE_ROW_BOUNDARY = /\|\s+\|/g;
const TABLE_SEPARATOR_ROW = /^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/;

function normalizeCompactTableLine(line: string): string {
  if (!line.includes('| |')) return line;

  const pipeIndexes = [...line.matchAll(/\|/g)]
    .map((match) => match.index ?? -1)
    .filter((index) => index >= 0);

  for (const index of pipeIndexes) {
    const table = line.slice(index);
    const normalizedTable = table.replace(TABLE_ROW_BOUNDARY, '|\n|');
    const rows = normalizedTable
      .split('\n')
      .map((row) => row.trim())
      .filter(Boolean);

    if (rows.length >= 2 && TABLE_SEPARATOR_ROW.test(rows[1])) {
      const prefix = line.slice(0, index).trimEnd();
      return prefix ? `${prefix}\n${normalizedTable}` : normalizedTable;
    }
  }

  return line;
}

function normalizeMarkdown(content: string): string {
  let inCodeFence = false;

  return content
    .split('\n')
    .map((line) => {
      if (/^\s*(```|~~~)/.test(line)) {
        inCodeFence = !inCodeFence;
        return line;
      }

      return inCodeFence ? line : normalizeCompactTableLine(line);
    })
    .join('\n');
}

/** Get renderable image src from ImageAttachment or legacy base64 string */
function getImageSrc(img: ImageAttachment | string): string {
  if (typeof img === 'string') return `data:image/png;base64,${img}`;
  return img.url || '';
}

export default function ChatBubble({ message }: Props) {
  const { lang } = useT();
  const isUser = message.role === 'user';
  const content = isUser ? message.content : normalizeMarkdown(message.content);
  const hasImages = message.images && message.images.length > 0;
  const activity = message.activity;

  // Don't render empty assistant messages (unless they have images)
  if (!isUser && !message.content && !hasImages && !activity) return null;

  return (
    <div className={`${styles.row} ${isUser ? styles.userRow : styles.botRow}`}>
      {!isUser && <div className={styles.avatar}>⬡</div>}
      <div className={`${styles.bubble} ${isUser ? styles.userBubble : styles.botBubble}`}>
        {!isUser && activity?.type === 'web_search' && (
          <div
            className={`${styles.webSearchActivity} ${activity.status === 'done' ? styles.webSearchDone : styles.webSearchActive}`}
            role="status"
            aria-live="polite"
          >
            <span className={styles.searchGlyph} aria-hidden="true" />
            <span className={styles.searchLabel}>{activity.label}</span>
            <span className={styles.searchDots} aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
          </div>
        )}
        {isUser
          ? content
          : (
            <>
              {message.content && (
                <div className={`${styles.markdown} ${message.streaming ? styles.markdownStreaming : ''}`}>
                  <Markdown remarkPlugins={[remarkGfm]}>{content}</Markdown>
                </div>
              )}
              {hasImages && (
                <div className={styles.imageGrid}>
                  {message.images!.map((img, idx) => {
                    const src = getImageSrc(img);
                    if (!src) return null;
                    return (
                      <a
                        key={typeof img === 'string' ? idx : img.id}
                        href={src}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.imageLink}
                      >
                        <img
                          src={src}
                          alt={`Screenshot ${idx + 1}`}
                          className={styles.screenshot}
                          loading="lazy"
                        />
                      </a>
                    );
                  })}
                </div>
              )}
            </>
          )
        }
        <span className={styles.time}>
          {new Date(message.timestamp).toLocaleTimeString(lang === 'zh' ? 'zh-CN' : 'en-US', { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
      {isUser && (
        <div className={`${styles.avatar} ${styles.userAvatar}`}>
          U
        </div>
      )}
    </div>
  );
}
