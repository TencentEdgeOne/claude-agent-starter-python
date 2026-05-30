const zh = {
  // Header
  "app.title": "Claude Agent Starter",
  "app.subtitle": "运行在 EdgeOne 环境中，支持沙箱工具、会话记忆与可观测",

  // Empty state
  "empty.title": "Claude Agent Starter",
  "empty.hint": "我是运行在 EdgeOne 环境中的 Claude 助手，可以调用沙箱工具、保存会话记忆，并帮助你完成各项任务。",
  "empty.features": "沙箱工具 · Store 会话记忆 · 自动可观测",

  // Chat input
  "chat.placeholder": "发消息…  ⏎ 发送 · Shift+⏎ 换行",
  "chat.hint": "由 Claude Agent SDK + EdgeOne Sandbox 驱动 · 仅供演示",

  // Preset questions
  "preset.1": "使用终端命令检查当前系统时间和操作系统版本。",
  "preset.2": "创建 /tmp/fib.py，写入计算斐波那契数列前 10 项的 Python 代码并执行，将结果打印出来。",
  "preset.4": "访问 https://edgeone.ai 并总结页面内容。",
  "preset.skill.webSearch": "使用网络搜索：“当前市值最高的5个公司”",

  // Tool indicators
  "tool.commands": "终端命令",
  "tool.files": "文件操作",
  "tool.codeRunner": "代码解释器",
  "tool.browser": "浏览器",

  // Skill indicators
  "skill.webSearch": "网络搜索",

  // Debug panel
  "debug.title": "传输流",
  "debug.events": "事件",
  "debug.clear": "清除",
  "debug.empty": "等待 SSE 事件...",
  "debug.emptyHint": "发送消息后，所有原始后端数据将在此处显示。",

  // Status & errors
  "status.error": "⚠️ 请求失败，请检查后端服务是否启动。",
  "status.stopped": "⏹ *已停止生成*",
  "status.backendError": "⚠️ 后端中断请求失败，服务端可能仍在运行。",

  // Language toggle
  "lang.switch": "English",
} as const;

export default zh;
