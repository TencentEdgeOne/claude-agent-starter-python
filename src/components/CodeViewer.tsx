import type React from 'react';
import styles from './CodeViewer.module.css';

/* -- Tiny inline helpers -- */
const Cmt  = ({ t }: { t: string }) => <span className={styles.cmt}>{t}</span>;
const Kw   = ({ t }: { t: string }) => <span className={styles.kw}>{t}</span>;
const Fn   = ({ t }: { t: string }) => <span className={styles.fn}>{t}</span>;
const Str  = ({ t }: { t: string }) => <span className={styles.str}>{t}</span>;
const Doc  = ({ t }: { t: string }) => <span className={styles.doc}>{t}</span>;
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
            <Fn t="ClaudeAgentOptions" /><Op t=", " /><Fn t="SdkMcpTool" />
          </L>
          <L n={2}>
            <Kw t="from " /><Va t="claude_agent_sdk" /><Kw t=" import " />
            <Fn t="create_sdk_mcp_server" /><Op t=", " /><Fn t="query" />
          </L>
          <L n={3}>
            <Kw t="from " /><Va t=".._model" /><Kw t=" import " />
            <Fn t="collect_gateway_env" /><Op t=", " /><Fn t="resolve_model_name" />
          </L>
          <L n={4} />

          {/* ═══ Handler ═══ */}
          <L n={5}>
            <Va t="SYSTEM_PROMPT" /><Op t=" = " /><Str t='"..."' />
          </L>
          <L n={6} />
          <L n={7}>
            <Kw t="async def " /><Fn t="handler" /><Op t="(" />
            <Va t="context" /><Op t="):" />
          </L>
          <L n={8}>
            <I /><Va t="message" /><Op t=" = " />
            <Va t="context" /><Op t="." /><Va t="request" /><Op t="." /><Va t="body" />
            <Op t="." /><Fn t="get" /><Op t="(" /><Str t='"message"' /><Op t=", " />
            <Str t='""' /><Op t=")" />
          </L>
          <L n={9}>
            <I /><Va t="conversation_id" /><Op t=" = " />
            <Va t="context" /><Op t="." /><Va t="conversation_id" />
          </L>
          <L n={10}>
            <I /><Va t="store" /><Op t=" = " />
            <Va t="context" /><Op t="." /><Va t="store" />
          </L>
          <L n={11} />

          {/* ═══ Step 1: Store save user msg ═══ */}
          <L n={12}>
            <I /><Cmt t="# 1. EdgeOne Store：保存用户消息，供历史恢复" />
          </L>
          <L n={13}>
            <I /><Kw t="await " /><Va t="store" /><Op t="." />
            <Fn t="append_message" /><Op t="(" />
            <Va t="conversation_id" /><Op t=", " />
            <Str t='"user"' /><Op t=", " /><Va t="message" /><Op t=")" />
          </L>
          <L n={14} />

          {/* ═══ Step 2: Session store ═══ */}
          <L n={15}>
            <I /><Cmt t="# 2. 注入 Claude Agent SDK 会话记忆" />
          </L>
          <L n={16}>
            <I /><Va t="session_store" /><Op t=" = " />
            <Va t="store" /><Op t="." /><Fn t="claude_session_store" /><Op t="()" />
          </L>
          <L n={17} />

          {/* ═══ Step 3: Platform tools ═══ */}
          <L n={18}>
            <I /><Cmt t="# 3. EdgeOne Tools：读取平台沙箱工具" />
          </L>
          <L n={19}>
            <I /><Va t="platform_tools" /><Op t=" = " />
            <Va t="context" /><Op t="." /><Va t="tools" /><Op t="." />
            <Fn t="all" /><Op t="()" />
          </L>
          <L n={20} />

          {/* ═══ Step 4: SdkMcpTool ═══ */}
          <L n={21}>
            <I /><Cmt t="# 4. 把 EdgeOne tools 包装成 MCP tools" />
          </L>
          <L n={22}>
            <I /><Va t="commands" /><Op t=" = " />
            <Fn t="SdkMcpTool" /><Op t="(" />
          </L>
          <L n={23}>
            <I level={2} /><Va t="name" /><Op t="=" /><Str t='"commands"' /><Op t="," />
          </L>
          <L n={24}>
            <I level={2} /><Va t="description" /><Op t="=" />
            <Str t='"Execute shell commands in EdgeOne sandbox"' /><Op t="," />
          </L>
          <L n={25}>
            <I level={2} /><Va t="input_schema" /><Op t="={" />
            <Str t='"type"' /><Op t=": " /><Str t='"object"' /><Op t=", " />
            <Str t='"properties"' /><Op t=": {" /><Str t='"cmd"' /><Op t=": ...}}," />
          </L>
          <L n={26}>
            <I level={2} /><Va t="handler" /><Op t="=" />
            <Kw t="lambda " /><Va t="args" /><Op t=": " />
            <Fn t="call_edgeone_tool" /><Op t="(" />
            <Va t="platform_tools" /><Op t=", " />
            <Str t='"commands"' /><Op t=", " /><Va t="args" /><Op t=")," />
          </L>
          <L n={27}>
            <I /><Op t=")" />
          </L>
          <L n={28}>
            <I /><Cmt t="# More tools can be added here" />
          </L>

          {/* -- Section Divider (gap removed) -- */}

          {/* ═══ Step 5: MCP Server ═══ */}
          <L n={29}>
            <I /><Cmt t="# 5. 注册 EdgeOne MCP Server" />
          </L>
          <L n={30}>
            <I /><Va t="edgeone" /><Op t=" = " />
            <Fn t="create_sdk_mcp_server" /><Op t="(" />
          </L>
          <L n={31}>
            <I level={2} /><Va t="name" /><Op t="=" /><Str t='"edgeone"' /><Op t="," />
          </L>
          <L n={32}>
            <I level={2} /><Va t="tools" /><Op t="=[" />
            <Va t="commands" /><Op t=", " /><Va t="files" /><Op t=", " />
            <Va t="code" /><Op t=", " /><Va t="browser" /><Op t="]," />
          </L>
          <L n={33}>
            <I /><Op t=")" />
          </L>
          <L n={34} />

          {/* ═══ Step 6: Agent Options ═══ */}
          <L n={35}>
            <I /><Cmt t="# 6. 创建 Claude Agent 运行参数" />
          </L>
          <L n={36}>
            <I /><Va t="options" /><Op t=" = " />
            <Fn t="ClaudeAgentOptions" /><Op t="(" />
          </L>
          <L n={37}>
            <I level={2} /><Va t="model" /><Op t="=" />
            <Fn t="resolve_model_name" /><Op t="()," />
          </L>
          <L n={38}>
            <I level={2} /><Va t="system_prompt" /><Op t="=" />
            <Va t="SYSTEM_PROMPT" /><Op t="," />
          </L>
          <L n={39}>
            <I level={2} /><Va t="session_store" /><Op t="=" />
            <Va t="session_store" /><Op t="," />
          </L>
          <L n={40}>
            <I level={2} /><Va t="mcp_servers" /><Op t="={" />
            <Str t='"edgeone"' /><Op t=": " /><Va t="edgeone" /><Op t="}," />
          </L>
          <L n={41}>
            <I level={2} /><Va t="allowed_tools" /><Op t="=[" />
            <Str t='"mcp__edgeone__commands"' /><Op t=", ...]," />
          </L>
          <L n={42}>
            <I level={2} /><Va t="permission_mode" /><Op t="=" />
            <Str t='"bypassPermissions"' /><Op t="," />
          </L>
          <L n={43}>
            <I level={2} /><Va t="env" /><Op t="=" />
            <Fn t="collect_gateway_env" /><Op t="()," />
          </L>
          <L n={44}>
            <I /><Op t=")" />
          </L>
          <L n={45} />

          {/* ═══ Step 7: Launch Agent ═══ */}
          <L n={46}>
            <I /><Cmt t="# 7. 启动 Claude Agent" />
          </L>
          <L n={47}>
            <I /><Va t="result" /><Op t=" = " />
            <Fn t="query" /><Op t="(" /><Va t="prompt" /><Op t="=" />
            <Va t="message" /><Op t=", " /><Va t="options" /><Op t="=" />
            <Va t="options" /><Op t=")" />
          </L>
          <L n={48}>
            <I /><Va t="assistant_text" /><Op t=" = " />
            <Kw t="await " /><Fn t="collect_assistant_text" /><Op t="(" />
            <Va t="result" /><Op t=")" />
          </L>
          <L n={49} />

          {/* ═══ Step 8: Save reply ═══ */}
          <L n={50}>
            <I /><Cmt t="# 8. 保存助手回复，供 /history 恢复" />
          </L>
          <L n={51}>
            <I /><Kw t="await " /><Va t="store" /><Op t="." />
            <Fn t="append_message" /><Op t="(" />
            <Va t="conversation_id" /><Op t=", " />
            <Str t='"assistant"' /><Op t=", " /><Va t="assistant_text" /><Op t=")" />
          </L>
          <L n={52}>
            <I /><Kw t="return " /><Op t="{" />
            <Str t='"answer"' /><Op t=": " /><Va t="assistant_text" /><Op t="}" />
          </L>
        </div>
      </div>

      {/* -- Footer tag -- */}
      <div className={styles.footer}>
        <span className={styles.footerDot} />
        <span>Claude Agent SDK · EdgeOne Store · MCP Server · 沙箱工具</span>
      </div>
    </div>
  );
}
