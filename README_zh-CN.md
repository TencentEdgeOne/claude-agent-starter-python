# Claude Agent Starter (Python)

基于 Anthropic Claude Agent SDK (Python) 的 EdgeOne Makers Agent 全栈项目模板。演示如何构建一个支持流式聊天、EdgeOne 沙箱工具（MCP 桥接）、会话记忆和工具指示灯的 Agent。

## 部署

[![使用 EdgeOne Pages 部署](https://cdnstatic.tencentcs.com/edgeone/pages/deploy.svg)](https://console.cloud.tencent.com/edgeone/makers/new?template=claude-agent-starter-python&from=within&fromAgent=1&agentLang=python)

## 功能

- **SSE 流式聊天** — 逐 token 推送 `text_delta`，命中工具时推送 `tool_called`
- **会话记忆** — 通过 `context.store.claude_session_store()` 保存 Claude transcript，支持跨请求上下文恢复
- **EdgeOne 沙箱工具** — commands、files、code_interpreter、browser，通过 MCP Server 桥接至 Claude Agent SDK
- **停止生成** — 通过平台 runtime cancel signal 真正中断 LLM 调用
- **工具灯状态** — 4 个动画指示灯，Claude 调用工具时实时点亮

## 目录结构

```text
claude-agent-starter-python/
├── agents/                        # 有状态的 EdgeOne Makers Agent Functions（Python）
│   ├── chat/
│   │   └── index.py              # POST /chat — SSE 流式聊天
│   ├── stop/
│   │   └── index.py              # POST /stop — 中断正在执行的 agent
│   ├── _model.py                 # 模型与网关环境变量配置（私有模块）
│   ├── _logger.py                # 日志工具（私有模块）
│   ├── config.json               # 路由配置
│   └── requirements.txt          # Python agent 依赖
├── cloud-functions/               # 无状态的 EdgeOne Pages Python cloud functions
│   ├── history/
│   │   └── index.py              # POST /history — 拉取对话消息
│   ├── conversations/
│   │   └── index.py              # POST /conversations — 列出某用户的会话
│   ├── clear-history/
│   │   └── index.py              # POST /clear-history — 清空某会话的消息
│   ├── delete-conversation/
│   │   └── index.py              # POST /delete-conversation — 彻底删除某会话
│   ├── _logger.py                # 日志工具
│   ├── _redact.py                # 日志敏感字段脱敏
│   └── requirements.txt          # Python cloud function 依赖
├── src/                           # React 前端（Vite + TypeScript）
│   ├── App.tsx                    # 主应用组件
│   ├── api.ts                    # 后端 API 封装（SSE 流式调用）
│   ├── types.ts                  # 类型定义
│   └── components/               # UI 组件
│       ├── ChatWindow.tsx        # 聊天窗口
│       ├── ChatBubble.tsx        # 消息气泡（支持 Markdown）
│       ├── ChatInput.tsx         # 输入框 + 预设 + 停止按钮
│       ├── CodeViewer.tsx        # 代码展示面板（CRT 风格）
│       ├── ToolIndicators.tsx    # 工具指示灯容器
│       └── ToolLamp.tsx          # 单个工具指示灯
├── index.html                    # 入口 HTML
├── package.json                  # 前端依赖（含 Claude Agent SDK）
├── edgeone.json                  # EdgeOne 部署配置
├── vite.config.ts                # Vite 配置
├── tsconfig.json                 # TypeScript 配置
└── uv.toml                       # Python 包管理镜像配置
```

> 以 `_` 开头的文件是私有模块，不会被 EdgeOne 映射为公开路由。
>
> **为什么后端拆成两个目录？** `agents/` 跑的是有状态、长连接的路由（活跃 SSE 流、按会话维度的 abort 信号）；`cloud-functions/` 跑的是只读写 `context.agent.store` 的短小无状态路由。两者拆开之后，历史记录 / 列表 / 删除等操作就不会和正在进行的对话争抢同一会话的锁。

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `AI_GATEWAY_API_KEY` | 是 | AI 网关 API Key（映射为 `ANTHROPIC_API_KEY` 传给 Claude SDK） |
| `AI_GATEWAY_BASE_URL` | 是 | AI 网关 Base URL（映射为 `ANTHROPIC_BASE_URL`） |
| `AI_GATEWAY_MODEL` | 否 | 模型名称（默认 `@makers/hy3-preview`） |
| `AI_GATEWAY_SMALL_MODEL` | 否 | 内部 SDK 子调用使用的小模型 |

## API 接口

| 端点 | 方法 | 所在目录 | 说明 |
|------|------|----------|------|
| `/chat` | POST | `agents/` | SSE 流式聊天，Header 带 `makers-conversation-id` |
| `/stop` | POST | `agents/` | 中断正在执行的 agent，Body 传 `{ "conversation_id": "..." }` |
| `/history` | POST | `cloud-functions/` | 获取对话历史，Body 传 `{ "conversation_id": "..." }` |
| `/conversations` | POST | `cloud-functions/` | 列出某用户的会话（分页）。Body 传 `{ "user_id": "...", "limit"?: 20, "after"?: "...", "before"?: "...", "order"?: "desc" }` |
| `/clear-history` | POST | `cloud-functions/` | 清空某会话的全部消息，Body 传 `{ "conversation_id": "..." }` |
| `/delete-conversation` | POST | `cloud-functions/` | 彻底删除一个会话，Body 传 `{ "conversation_id": "..." }` |

### SSE 事件

```
event: text_delta     data: {"delta":"你好"}
event: tool_called    data: {"tool":"commands"}
event: ping           data: {"ts":1710000000000}
event: error          data: {"message":"..."}
event: done           data: {"stopped":false}
```

## 架构

### 后端（`agents/` + `cloud-functions/`)

`agents/` 是有状态的部分，持有正在进行的 SSE 流以及对应的 AbortSignal：

1. **`collect_gateway_env()`** — 将 `AI_GATEWAY_*` 环境变量映射为 `ANTHROPIC_*` 传给 Claude Agent SDK 子进程
2. **`context.tools.all()`** — 提取 EdgeOne 沙箱工具并包装为 Claude MCP tools
3. **`create_sdk_mcp_server()`** — 将 EdgeOne 工具注册为 Claude Agent SDK 的 MCP Server
4. **`context.store.claude_session_store()`** — 提供 session 持久化，用于多轮对话记忆
5. **`query(prompt, options)`** — 启动 Claude Agent 并流式输出
6. **`store.append_message()`** — 保存用户 / 助手消息，方便后续恢复

`cloud-functions/` 负责无状态的会话存储 CRUD（history / conversations / clear-history / delete-conversation）。这些路由直接读写 `context.agent.store`，不会启动 agent，也就不会和正在进行的对话抢同一个会话锁。

### 前端（`src/`）

- `App.tsx` — 编排聊天面板 + 代码查看器，管理 SSE 流
- `api.ts` — SSE 解析，分发 `onTextDelta`、`onToolCalled`、`onDone`、`onError`
- `components/CodeViewer.tsx` — 静态代码展示面板（琥珀 CRT 风格），展示 Agent 创建流程
- `components/ToolIndicators.tsx` — 模型调用工具时的动画指示灯

## 本地开发

```bash
# 安装前端依赖
npm install

# 安装后端 Python 依赖
pip install -r requirements.txt

# 启动 EdgeOne 本地开发（前后端同时启动）
edgeone makers dev
```
