# 从 `claude-agent-starter` 同步 Skill、预制问题、SSE 调试面板与右侧面板切换方案

目标项目：`/Users/wenyiqing/Desktop/agents/agent-example/claude-agent-starter-python`

参考项目：`/Users/wenyiqing/Desktop/agents/agent-example/claude-agent-starter`

需要同步的功能：

1. 将 Python 版项目的 skills 改成和 TS 版项目一致的 `smart-translator`，并同步前端预制问题；
2. 增加 SSE 调试面板 `DebugPanel`；
3. 首页右侧默认展示代码信息 `CodeViewer`，用户开始执行后切换为 SSE 调试面板；
4. 同步 `skills loading...` 展示等前端细节。

---

## 1. 当前差异概览

### 1.1 参考项目现状：`claude-agent-starter`

参考项目已经具备：

- `.claude/skills/smart-translator/SKILL.md`；
- 前端 preset 已包含 `preset.skill.smartTranslator`；
- `ChatInput.tsx` 中预制问题列表为：

```ts
const PRESET_KEYS = ['preset.1', 'preset.2', 'preset.4', 'preset.skill.smartTranslator'] as const;
```

- `src/components/DebugPanel.tsx` 和 `DebugPanel.module.css`；
- `App.tsx` 中有：
  - `debugEvents`；
  - `skillsLoading`；
  - `rightPanelMode: 'code' | 'debug'`；
  - 首页右侧 `CodeViewer`；
  - 执行后切换为 `DebugPanel`；
  - `skills_loaded` 后展示 `skills loading...`。

### 1.2 目标项目现状：`claude-agent-starter-python`

目标项目当前状态：

#### Skills

当前存在 3 个旧 skill：

```txt
.claude/skills/test-writer/SKILL.md
.claude/skills/code-review/SKILL.md
.claude/skills/api-docs-generator/SKILL.md
```

需要替换为：

```txt
.claude/skills/smart-translator/SKILL.md
```

#### 前端 preset

当前 `src/components/ChatInput.tsx`：

```ts
const PRESET_KEYS = ['preset.1', 'preset.2', 'preset.3', 'preset.4'] as const;
```

需要改成和参考项目一致：

```ts
const PRESET_KEYS = ['preset.1', 'preset.2', 'preset.4', 'preset.skill.smartTranslator'] as const;
```

#### 右侧面板

当前 `src/App.tsx` 右侧固定显示：

```tsx
<div className={styles.codePanel}>
  <CodeViewer />
</div>
```

目标：

- 初始仍显示 `CodeViewer`；
- 用户开始执行后切换到 `DebugPanel`；
- 清空历史后切回 `CodeViewer`。

#### SSE 调试面板

目标项目目前没有：

```txt
src/components/DebugPanel.tsx
src/components/DebugPanel.module.css
```

需要从参考项目同步。

#### API 层

目标项目当前 `src/api.ts`：

- 没有 `RawSseEvent`；
- `StreamCallbacks` 没有 `onRawEvent`；
- `dispatchSseChunk` 解析事件后只分发业务回调，没有把原始事件推给前端 DebugPanel；
- 没有 `SkillInfo` / `SkillLoadedPayload` / `onSkillAvailable` / `onSkillLoaded`。

需要同步参考项目中的 SSE raw event 能力。

---

## 2. Skill 同步方案

### 2.1 删除旧 Skills

删除目标项目中：

```txt
.claude/skills/test-writer/SKILL.md
.claude/skills/code-review/SKILL.md
.claude/skills/api-docs-generator/SKILL.md
```

原因：当前 demo 只需要一个简单、稳定、容易展示的 skill，避免用户误以为存在多个可展示能力。

### 2.2 新增 `smart-translator`

新增文件：

```txt
.claude/skills/smart-translator/SKILL.md
```

内容与参考项目保持一致：

```md
---
name: smart-translator
description: Translate text between Chinese and English while preserving tone, formatting, terminology, and Markdown structure. Use when the user asks to translate, localize, polish bilingual content, or adapt copy for product pages.
---

# Smart Translator

## Instructions

When translating or localizing text:

1. Detect the source language automatically.
2. Translate Chinese to English, or English to Chinese, unless the user specifies another target language.
3. Preserve Markdown, lists, tables, inline code, links, placeholders, and product names.
4. Keep technical terms accurate and consistent.
5. Adapt the tone according to the user's request.
6. If the user does not specify a tone, use a clear, professional, and concise tone.
7. Do not add unrelated explanation.

## Output Format

Return:

```md
## Translation

...

## Notes

- ...
```

Only include `Notes` when there are important terminology, tone, or localization decisions.

## Rules

- Do not change product names unless explicitly requested.
- Preserve placeholders, variables, command names, API names, and code identifiers.
- Preserve Markdown structure whenever possible.
- Keep the translation natural rather than literal when product copy requires localization.
- Respond in the same language as the user unless the user asks otherwise.
```

---

## 3. 预制问题同步方案

### 3.1 修改 `ChatInput.tsx`

文件：`src/components/ChatInput.tsx`

将：

```ts
const PRESET_KEYS = ['preset.1', 'preset.2', 'preset.3', 'preset.4'] as const;
```

改为：

```ts
const PRESET_KEYS = ['preset.1', 'preset.2', 'preset.4', 'preset.skill.smartTranslator'] as const;
```

注意：目标项目当前使用：

```ts
import { useT, MessageKeys } from '../i18n';
```

并在渲染时使用：

```tsx
{t(key as MessageKeys)}
```

这个写法可以保留。

### 3.2 修改中文 i18n

文件：`src/i18n/zh.ts`

将原来的 `preset.2` 和 `preset.3` 合并，保持和参考项目一致：

```ts
"preset.1": "使用终端命令检查当前系统时间和操作系统版本。",
"preset.2": "创建 /tmp/fib.py，写入计算斐波那契数列前 10 项的 Python 代码并执行，将结果打印出来。",
"preset.4": "访问 https://edgeone.ai 并总结页面内容。",
"preset.skill.smartTranslator": "用 smart-translator skill 翻译成英文：EdgeOne Makers Agent 帮助开发者快速构建 AI Agent 应用。",
```

新增 skill 指示文案：

```ts
// Skill indicators
"skill.smartTranslator": "智能翻译",
```

新增 debug 面板文案：

```ts
// Debug panel
"debug.title": "SSE 调试",
"debug.events": "事件",
"debug.clear": "清除",
"debug.empty": "等待 SSE 事件...",
"debug.emptyHint": "发送消息后，所有原始后端数据将在此处显示。",
```

### 3.3 修改英文 i18n

文件：`src/i18n/en.ts`

同步：

```ts
"preset.1": "Use terminal commands to check the current system time and OS version.",
"preset.2": "Create /tmp/fib.py, write Python code to calculate the first 10 Fibonacci numbers, execute it, and print the result.",
"preset.4": "Visit https://edgeone.ai and summarize the page content.",
"preset.skill.smartTranslator": "Use smart-translator skill to translate into Chinese: EdgeOne Makers Agent helps developers quickly build AI Agent apps.",
```

新增：

```ts
// Skill indicators
"skill.smartTranslator": "Smart Translator",
```

新增 debug 面板文案：

```ts
// Debug panel
"debug.title": "SSE Debug",
"debug.events": "events",
"debug.clear": "Clear",
"debug.empty": "Waiting for SSE events...",
"debug.emptyHint": "After sending a message, all raw backend data will be displayed here.",
```

---

## 4. 后端 SSE Skill 事件同步方案

目标项目是 Python 后端，对应文件：

```txt
agents/chat/_stream.py
agents/chat/index.py
```

### 4.1 当前后端已有能力

目标项目当前 `agents/chat/index.py` 已经配置：

```py
setting_sources=["project"],
skills="all",
```

并在开始 query 前发送：

```py
yield sse_event("skills_loaded", {
    "skills": "all",
    "setting_sources": ["project"],
})
```

这可以触发前端 `skills loading...` 展示。

### 4.2 新增 `PROJECT_SKILLS`

文件：`agents/chat/_stream.py`

新增常量：

```py
PROJECT_SKILLS = [
    {
        "name": "smart-translator",
        "label": "智能翻译",
        "description": "Translate text between Chinese and English while preserving tone, formatting, terminology, and Markdown structure.",
    }
]
```

### 4.3 在 `index.py` 中发送 `skills_available`

从 `_stream.py` 引入 `PROJECT_SKILLS`：

```py
from ._stream import StreamState, iter_query_messages, sdk_message_to_sse, sse_event, PROJECT_SKILLS
```

在 `skills_loaded` 后继续发送：

```py
yield sse_event("skills_available", {
    "skills": PROJECT_SKILLS,
})
```

这用于前端展示当前可用 skill。

### 4.4 检测 `load_skill` 并发送 `skill_loaded`

目标项目 `_stream.py` 当前已经会处理 `tool_use`，并发送：

```py
events.append(sse_event("tool_called", {"tool": tool_name}))
```

需要在两个位置补充 `load_skill` 检测：

1. `_handle_stream_event` 的 `content_block_start` 分支；
2. `_handle_assistant_message` 的 `tool_use` 分支。

推荐新增工具函数：

```py
def _extract_skill_name_from_tool_input(tool_input: Any) -> str | None:
    if isinstance(tool_input, dict):
        value = tool_input.get("skill") or tool_input.get("name") or tool_input.get("skillName")
        return value if isinstance(value, str) else None
    return None
```

在检测到 `load_skill` 时：

```py
if tool_name == "load_skill" or "load_skill" in raw_name:
    skill_name = _extract_skill_name_from_tool_input(tool_input)
    if skill_name:
        events.append(sse_event("skill_loaded", {
            "name": skill_name,
            "status": "loaded",
        }))
```

注意：如果 Python SDK 没有暴露实际 `load_skill` 工具事件，前端仍可通过 `skills_loaded` 展示 `skills loading...`，通过 `skills_available` 展示 skill 可用状态；不要把 `skills_available` 误标成“正在使用”。

---

## 5. 前端 API 层同步方案

文件：`src/api.ts`

### 5.1 新增 `RawSseEvent`

```ts
export interface RawSseEvent {
  eventType: string;
  data: unknown;
  raw: string;
  timestamp: number;
}
```

### 5.2 新增 Skill 类型

```ts
export interface SkillInfo {
  name: string;
  label?: string;
  description?: string;
}

export interface SkillLoadedPayload {
  name: string;
  status: 'loaded';
}
```

### 5.3 扩展 `StreamCallbacks`

当前：

```ts
export interface StreamCallbacks {
  onTextDelta: (delta: string) => void;
  onToolCalled: (toolName: string) => void;
  onImage: (payload: ImageSsePayload) => void;
  onDone: () => void;
  onError: (err: Error) => void;
}
```

改为：

```ts
export interface StreamCallbacks {
  onTextDelta: (delta: string) => void;
  onToolCalled: (toolName: string) => void;
  onImage: (payload: ImageSsePayload) => void;
  onSkillAvailable?: (skills: SkillInfo[]) => void;
  onSkillLoaded?: (payload: SkillLoadedPayload) => void;
  onDone: () => void;
  onError: (err: Error) => void;
  onRawEvent?: (event: RawSseEvent) => void;
}
```

### 5.4 在 `dispatchSseChunk` 中推送 raw event

解析 JSON 后，先推送 raw event：

```ts
const parsed = JSON.parse(data);

if (cb.onRawEvent) {
  cb.onRawEvent({
    eventType,
    data: parsed,
    raw: data,
    timestamp: Date.now(),
  });
}
```

解析失败时也推送：

```ts
if (cb.onRawEvent) {
  cb.onRawEvent({
    eventType,
    data: null,
    raw: data,
    timestamp: Date.now(),
  });
}
```

### 5.5 新增事件分支

```ts
case 'skills_available':
  cb.onSkillAvailable?.(parsed.skills || []);
  break;
case 'skill_loaded':
  cb.onSkillLoaded?.({ name: parsed.name, status: 'loaded' });
  break;
```

### 5.6 注意修复参考项目里的小问题

参考项目 `src/api.ts` 中 `skill_loaded` 分支附近存在重复 `break`：

```ts
case 'skill_loaded':
  cb.onSkillLoaded?.({ name: parsed.name, status: 'loaded' });
  break;
  break;
```

目标项目同步时不要复制重复 `break`。

---

## 6. 新增 DebugPanel 组件

从参考项目复制：

```txt
claude-agent-starter/src/components/DebugPanel.tsx
claude-agent-starter/src/components/DebugPanel.module.css
```

到目标项目：

```txt
claude-agent-starter-python/src/components/DebugPanel.tsx
claude-agent-starter-python/src/components/DebugPanel.module.css
```

### 6.1 `DebugPanel.tsx` 要点

组件 props：

```ts
interface Props {
  events: RawSseEvent[];
  onClear: () => void;
}
```

核心行为：

- 展示事件数量；
- 支持清除；
- 空状态展示；
- 事件变化时滚动到底部；
- `JSON.stringify(evt.data, null, 2)` 展示结构化事件数据。

### 6.2 CSS 注意事项

参考项目的 `DebugPanel.module.css` 已有：

- `.type_text_delta`
- `.type_tool_called`
- `.type_done`
- `.type_error`
- `.type_ping`
- `.type_skills_loaded`
- `.type_debug_msg`
- `.type_unknown`

建议目标项目同步后额外补充：

```css
.type_skills_available {
  color: #00ffa3;
  background: rgba(0, 255, 163, 0.15);
}

.type_skill_loaded {
  color: #4ade80;
  background: rgba(74, 222, 128, 0.15);
}

.type_image {
  color: #38bdf8;
  background: rgba(56, 189, 248, 0.12);
}
```

---

## 7. App.tsx 前端状态同步方案

文件：`src/App.tsx`

### 7.1 新增 import

当前目标项目已有：

```ts
import CodeViewer from './components/CodeViewer';
```

需要新增：

```ts
import DebugPanel from './components/DebugPanel';
import type { RawSseEvent } from './api';
```

### 7.2 新增状态

在现有 state 附近新增：

```ts
const [debugEvents, setDebugEvents] = useState<RawSseEvent[]>([]);
const [skillsLoading, setSkillsLoading] = useState(false);
const [rightPanelMode, setRightPanelMode] = useState<'code' | 'debug'>('code');
```

含义：

- `debugEvents`：DebugPanel 的事件源；
- `skillsLoading`：header 中显示 `skills loading...`；
- `rightPanelMode`：右侧展示 `CodeViewer` 或 `DebugPanel`。

### 7.3 发送消息时切换右侧面板

在 `handleSend` 开始处：

```ts
initDoneRef.current = true;
setRightPanelMode('debug');
```

放在最前面，保证用户点击后立即切换到 SSE 调试面板。

### 7.4 接收 raw SSE 事件

在 `sendMessageStream` callbacks 中新增：

```ts
onRawEvent(event) {
  setRightPanelMode('debug');
  setDebugEvents(prev => [...prev, event]);

  if (event.eventType === 'skills_loaded') {
    setSkillsLoading(true);
    setTimeout(() => setSkillsLoading(false), 2000);
  }
},
```

这样实现与参考项目一致的细节：

- 收到任意 SSE raw event 时，右侧保持 DebugPanel；
- 收到 `skills_loaded` 时，header 短暂显示 `skills loading...`。

### 7.5 可选：使用 Skill 回调

如果 `src/api.ts` 实现了 `onSkillAvailable` / `onSkillLoaded`，后续可进一步显示具体 skill 指示器。但本次需求只要求 `skills loading...` 展示保持一致，因此最小实现可以先不在 UI 中展示具体 skill 列表。

### 7.6 清空历史时恢复 CodeViewer

在 `handleClearHistory` 中新增：

```ts
setDebugEvents([]);
setRightPanelMode('code');
setSkillsLoading(false);
```

保留现有：

```ts
setMessages([]);
initDoneRef.current = false;
```

### 7.7 Header 中展示 `skills loading...`

参考项目写法：

```tsx
<ToolIndicators lamps={lamps} />
{skillsLoading && <span className={styles.skillsLoading}>skills loading...</span>}
```

目标项目 header 当前只有：

```tsx
<ToolIndicators lamps={lamps} />
```

改为：

```tsx
<ToolIndicators lamps={lamps} />
{skillsLoading && <span className={styles.skillsLoading}>skills loading...</span>}
```

### 7.8 右侧条件渲染

当前：

```tsx
<div className={styles.codePanel}>
  <CodeViewer />
</div>
```

改为：

```tsx
<div className={styles.codePanel}>
  {rightPanelMode === 'code' ? (
    <CodeViewer />
  ) : (
    <DebugPanel events={debugEvents} onClear={() => setDebugEvents([])} />
  )}
</div>
```

行为：

- 初始显示代码信息；
- 执行后显示 SSE 调试日志；
- 执行结束后保持 SSE 调试日志；
- 清空历史后恢复代码信息。

---

## 8. App.module.css 同步方案

文件：`src/App.module.css`

目标项目当前没有 `skillsLoading` 样式，需要从参考项目同步：

```css
.skillsLoading {
  font-size: .7rem;
  font-family: var(--font-mono);
  color: #4ade80;
  letter-spacing: .03em;
  animation: skillsFadeIn 300ms ease-out both, skillsFadeOut 600ms ease-in 1400ms both;
}

@keyframes skillsFadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes skillsFadeOut {
  from { opacity: 1; }
  to   { opacity: 0; }
}
```

同时建议将 `.codePanel` 的 `overflow` 调整为和参考项目一致：

```css
.codePanel {
  flex: 0 0 42%;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: visible;
}
```

如果 `DebugPanel` 出现滚动或高度问题，优先检查：

- `.codePanel` 是否 `min-height: 0`；
- `DebugPanel.module.css .panel` 是否 `height: 100%; min-height: 0`；
- `DebugPanel.module.css .body` 是否 `flex: 1; min-height: 0; overflow-y: auto`。

---

## 9. 推荐实施顺序

1. 删除目标项目旧 skills：
   - `test-writer`
   - `code-review`
   - `api-docs-generator`
2. 新增 `.claude/skills/smart-translator/SKILL.md`；
3. 修改 `src/i18n/zh.ts` 和 `src/i18n/en.ts`；
4. 修改 `src/components/ChatInput.tsx` 的 `PRESET_KEYS`；
5. 修改 Python 后端：
   - `_stream.py` 增加 `PROJECT_SKILLS`；
   - `_stream.py` 增加 `load_skill` 检测和 `skill_loaded` SSE；
   - `index.py` 发送 `skills_available`；
6. 修改 `src/api.ts`：
   - 增加 `RawSseEvent`；
   - 增加 `onRawEvent`；
   - 增加 `skills_available` / `skill_loaded` 分支；
7. 复制新增：
   - `DebugPanel.tsx`
   - `DebugPanel.module.css`
8. 修改 `src/App.tsx`：
   - 引入 `DebugPanel`；
   - 新增 `debugEvents`；
   - 新增 `skillsLoading`；
   - 新增 `rightPanelMode`；
   - `handleSend` 切换到 debug；
   - `onRawEvent` 记录事件并处理 `skills_loaded`；
   - `handleClearHistory` 清空 debug 并切回 code；
   - 右侧条件渲染 `CodeViewer` / `DebugPanel`；
9. 修改 `src/App.module.css`，增加 `skillsLoading` 样式并确认右侧布局；
10. 运行 TypeScript 检查和前端启动验证。

---

## 10. 验证清单

### 10.1 Skill 与 preset

- `.claude/skills` 下只保留 `smart-translator`；
- 页面 preset 包含 `smart-translator` 翻译问题；
- `preset.2` 已合并成 `/tmp/fib.py` 斐波那契任务；
- 页面不再显示旧的 `preset.3`；
- 中英文切换均正常。

### 10.2 后端 SSE

发送一条消息后，DebugPanel 应能看到：

- `skills_loaded`；
- `skills_available`；
- `text_delta`；
- `tool_called`，如果触发工具；
- `skill_loaded`，如果 SDK 暴露 `load_skill`；
- `done`。

### 10.3 右侧面板切换

- 首次进入页面：右侧显示 `CodeViewer`；
- 点击任意 preset：右侧立即切到 `DebugPanel`；
- SSE 事件持续追加；
- 执行结束后仍保持 `DebugPanel`；
- 点击清空历史后：右侧回到 `CodeViewer`，debugEvents 清空。

### 10.4 `skills loading...`

- 收到 `skills_loaded` 时，header 显示 `skills loading...`；
- 约 2 秒后自动隐藏；
- 不影响工具灯展示；
- 不影响语言切换。

### 10.5 回归验证

- 文本流式输出正常；
- 停止生成正常；
- 工具灯正常亮起；
- 图片 SSE / IndexedDB 图片持久化功能不受影响；
- history 恢复不受影响；
- `npm run build` 或 `npx tsc --noEmit` 通过。

---

## 11. 注意事项

- 目标项目是 Python 后端，不要直接照搬 TS 后端 `_stream.ts`；应按 Python `_stream.py` 的 `sse_event(...)` 模式实现。
- `skills_loaded` 是“配置已启用”，`skill_loaded` 才是“模型实际加载了 skill”；前端 `skills loading...` 可以基于 `skills_loaded`，但不要把它等同于实际触发 skill。
- `DebugPanel` 依赖 `onRawEvent`，所以必须先改 `src/api.ts`，否则面板没有事件来源。
- 不建议使用 `debugEvents.length > 0` 判断右侧面板模式；应使用显式 `rightPanelMode`。
- 清空 DebugPanel 按钮只清空事件，不应该自动切回 `CodeViewer`；只有清空聊天历史时才切回 `CodeViewer`。
- 如果 `skill_loaded` 无法出现，优先查看 DebugPanel 中 `tool_called` / raw event 的实际结构，再调整 Python 后端的 `load_skill` 检测逻辑。
