import type React from 'react';
import styles from './CodeViewer.module.css';

/* -- Tiny inline helpers -- */
const Cmt  = ({ t }: { t: string }) => <span className={styles.cmt}>{t}</span>;
const Kw   = ({ t }: { t: string }) => <span className={styles.kw}>{t}</span>;
const Fn   = ({ t }: { t: string }) => <span className={styles.fn}>{t}</span>;
const Str  = ({ t }: { t: string }) => <span className={styles.str}>{t}</span>;
const Op   = ({ t }: { t: string }) => <span className={styles.op}>{t}</span>;
const Va   = ({ t }: { t: string }) => <span className={styles.va}>{t}</span>;

interface LineProps { n: number; children?: React.ReactNode }
const L = ({ n, children }: LineProps) => (
  <div className={styles.line}>
    <span className={styles.ln}>{String(n).padStart(2, ' ')}</span>
    <span className={styles.lc}>{children ?? ' '}</span>
  </div>
);

const I = ({ level = 1 }: { level?: number }) => (
  <>{Array.from({ length: level }).map((_, i) => (
    <span key={i} className={styles.indent} />
  ))}</>
);

export default function CodeViewer() {
  return (
    <div className={styles.panel}>
      {/* -- Header -- */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.fileIcon}>&#x2B21;</span>
          <span className={styles.filename}>handler<span className={styles.sep}>.</span>py</span>
        </div>
        <span className={styles.badge}>READ ONLY</span>
      </div>

      {/* -- Code body -- */}
      <div className={styles.body}>
        <div className={styles.scanline} aria-hidden />

        <div className={styles.code}>
          {/* ═══ Imports ═══ */}
          <L n={1}>
            <Kw t="from " /><Va t="claude_agent_sdk" /><Kw t=" import " />
            <Fn t="ClaudeAgentOptions" /><Op t=", " /><Fn t="create_sdk_mcp_server" /><Op t=", " /><Fn t="query" />
          </L>
          <L n={2}>
            <Kw t="from " /><Va t=".._model" /><Kw t=" import " />
            <Fn t="collect_gateway_env" /><Op t=", " /><Fn t="resolve_model_name" />
          </L>
          <L n={3} />

          {/* ═══ Handler ═══ */}
          <L n={4}>
            <Va t="SYSTEM_PROMPT" /><Op t=" = " /><Str t='"..."' />
          </L>
          <L n={5} />
          <L n={6}>
            <Kw t="async def " /><Fn t="handler" /><Op t="(" />
            <Va t="context" /><Op t="):" />
          </L>
          <L n={7}>
            <I /><Va t="message" /><Op t=" = " />
            <Va t="context" /><Op t="." /><Va t="request" /><Op t="." /><Va t="body" />
            <Op t="." /><Fn t="get" /><Op t="(" /><Str t='"message"' /><Op t=", " />
            <Str t='""' /><Op t=")" />
          </L>
          <L n={8}>
            <I /><Va t="store" /><Op t=" = " />
            <Va t="context" /><Op t="." /><Va t="store" />
          </L>
          <L n={9}>
            <I /><Va t="cid" /><Op t=" = " />
            <Va t="context" /><Op t="." /><Va t="conversation_id" />
          </L>
          <L n={10} />

          {/* ═══ Step 1: Store save user msg ═══ */}
          <L n={11}>
            <I /><Cmt t="# 1. EdgeOne Store: save user message for history" />
          </L>
          <L n={12}>
            <I /><Kw t="await " /><Va t="store" /><Op t="." />
            <Fn t="append_message" /><Op t="(" />
            <Va t="cid" /><Op t=", " />
            <Str t='"user"' /><Op t=", " /><Va t="message" /><Op t=")" />
          </L>
          <L n={13} />

          {/* ═══ Step 2: Session store ═══ */}
          <L n={14}>
            <I /><Cmt t="# 2. Inject Claude Agent SDK session memory" />
          </L>
          <L n={15}>
            <I /><Va t="session_store" /><Op t=" = " />
            <Va t="store" /><Op t="." /><Fn t="claude_session_store" /><Op t="()" />
          </L>
          <L n={16} />

          {/* ═══ Step 3: One-click tools conversion ═══ */}
          <L n={17}>
            <I /><Cmt t="# 3. EdgeOne Tools: one-click convert to Claude MCP Server" />
          </L>
          <L n={18}>
            <I /><Va t="edgeone_mcp" /><Op t=" = " />
            <Va t="context" /><Op t="." /><Va t="tools" /><Op t="." />
            <Fn t="to_claude_mcp_server" /><Op t="(" />
            <Str t='"edgeone"' /><Op t=")" />
          </L>
          <L n={19}>
            <I /><Va t="mcp_server" /><Op t=" = " />
            <Fn t="create_sdk_mcp_server" /><Op t="(" />
          </L>
          <L n={20}>
            <I level={2} /><Va t="name" /><Op t="=" />
            <Va t="edgeone_mcp" /><Op t="." /><Va t="name" /><Op t="," />
          </L>
          <L n={21}>
            <I level={2} /><Va t="tools" /><Op t="=" />
            <Va t="edgeone_mcp" /><Op t="." /><Va t="tools" /><Op t="," />
          </L>
          <L n={22}>
            <I /><Op t=")" />
          </L>
          <L n={23} />

          {/* ═══ Step 4: Agent Options ═══ */}
          <L n={24}>
            <I /><Cmt t="# 4. Build Agent run options" />
          </L>
          <L n={25}>
            <I /><Va t="options" /><Op t=" = " />
            <Fn t="ClaudeAgentOptions" /><Op t="(" />
          </L>
          <L n={26}>
            <I level={2} /><Va t="model" /><Op t="=" />
            <Fn t="resolve_model_name" /><Op t="()," />
          </L>
          <L n={27}>
            <I level={2} /><Va t="system_prompt" /><Op t="=" />
            <Va t="SYSTEM_PROMPT" /><Op t="," />
          </L>
          <L n={28}>
            <I level={2} /><Va t="session_store" /><Op t="=" />
            <Va t="session_store" /><Op t="," />
          </L>
          <L n={29}>
            <I level={2} /><Va t="mcp_servers" /><Op t="={" />
            <Va t="edgeone_mcp" /><Op t="." /><Va t="name" /><Op t=": " />
            <Va t="mcp_server" /><Op t="}," />
          </L>
          <L n={30}>
            <I level={2} /><Va t="allowed_tools" /><Op t="=" />
            <Va t="edgeone_mcp" /><Op t="." /><Va t="allowed_tools" /><Op t="," />
          </L>
          <L n={31}>
            <I level={2} /><Va t="env" /><Op t="=" />
            <Fn t="collect_gateway_env" /><Op t="()," />
          </L>
          <L n={32}>
            <I /><Op t=")" />
          </L>
          <L n={33} />

          {/* ═══ Step 5: Launch Agent ═══ */}
          <L n={34}>
            <I /><Cmt t="# 5. Launch Claude Agent" />
          </L>
          <L n={35}>
            <I /><Va t="result" /><Op t=" = " />
            <Fn t="query" /><Op t="(" /><Va t="prompt" /><Op t="=" />
            <Va t="message" /><Op t=", " /><Va t="options" /><Op t="=" />
            <Va t="options" /><Op t=")" />
          </L>
          <L n={36}>
            <I /><Va t="assistant_text" /><Op t=" = " />
            <Kw t="await " /><Fn t="collect_assistant_text" /><Op t="(" />
            <Va t="result" /><Op t=")" />
          </L>
          <L n={37} />

          {/* ═══ Step 6: Save reply ═══ */}
          <L n={38}>
            <I /><Cmt t="# 6. EdgeOne Store: save assistant reply for /history" />
          </L>
          <L n={39}>
            <I /><Kw t="await " /><Va t="store" /><Op t="." />
            <Fn t="append_message" /><Op t="(" />
            <Va t="cid" /><Op t=", " />
            <Str t='"assistant"' /><Op t=", " /><Va t="assistant_text" /><Op t=")" />
          </L>
          <L n={40}>
            <I /><Kw t="return " /><Op t="{" />
            <Str t='"answer"' /><Op t=": " /><Va t="assistant_text" /><Op t="}" />
          </L>
        </div>
      </div>

      {/* -- Footer tag -- */}
      <div className={styles.footer}>
        <span className={styles.footerDot} />
        <span>Claude Agent SDK · EdgeOne Store · MCP Tools</span>
      </div>
    </div>
  );
}
