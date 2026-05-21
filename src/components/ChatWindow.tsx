import { useEffect, useRef } from 'react';
import type { Message } from '../types';
import ChatBubble from './ChatBubble';
import styles from './ChatWindow.module.css';

interface Props {
  messages: Message[];
  loading: boolean;
}

export default function ChatWindow({ messages, loading }: Props) {
  const windowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // 没有内容时不需要滚动
    if (messages.length === 0 && !loading) return;
    // 直接操作容器 scrollTop，只滚动 ChatWindow 内部
    // 避免 scrollIntoView 滚动所有祖先元素导致 header 消失
    const el = windowRef.current;
    if (!el) return;
    // 流式输出期间用 instant 避免 smooth 动画堆积导致抖动，结束后再用 smooth
    el.scrollTo({ top: el.scrollHeight, behavior: loading ? 'instant' : 'smooth' });
  }, [messages, loading]);

  return (
    <div ref={windowRef} className={styles.window}>
      {messages.length === 0 && (
        <div className={styles.empty}>
          <span className={styles.emptyIcon}>⬡</span>
          <p className={styles.emptyTitle}>Claude Agent 助手已就绪</p>
          <p className={styles.emptyHint}>
            我是运行在 EdgeOne 环境中的 Claude 助手，可以调用沙箱工具、保存会话记忆，并帮助你完成各项任务。
          </p>
          <p className={styles.emptyFeatures}>
            沙箱工具 · Store 会话记忆 · 自动可观测
          </p>
        </div>
      )}

      {messages.map(msg => (
        <ChatBubble key={msg.id} message={msg} />
      ))}

      {/* 仅当 loading 且助手消息还没有内容流入时才显示等待动画 */}
      {loading && !(messages.length > 0 && messages[messages.length - 1].role === 'assistant' && messages[messages.length - 1].content.length > 0) && (
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
