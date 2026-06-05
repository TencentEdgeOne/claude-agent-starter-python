const en = {
  // Header
  "app.title": "Claude Agent Starter",
  "app.subtitle": "Running on EdgeOne Makers with sandbox tools, session memory & observability",

  // Empty state
  "empty.title": "Claude Agent Starter",
  "empty.hint": "I'm a Claude assistant running on EdgeOne. I can call sandbox tools, persist session memory, and help you with debugging, file management, code execution, and web browsing.",
  "empty.features": "Sandbox Tools · Store Memory · Observability",

  // Chat input
  "chat.placeholder": "Type a message...  ⏎ Send · Shift+⏎ Newline",
  "chat.hint": "Powered by Claude Agent SDK + EdgeOne Makers · Demo only",

  // Preset questions
  "preset.1": "Use terminal commands to check the current system time and OS version.",
  "preset.2": "Create /tmp/fib.py, write Python code to calculate the first 10 Fibonacci numbers, execute it, and print the result.",
  "preset.4": "Visit https://edgeone.ai and summarize the page content.",
  "preset.screenshotEdgeOne": "Take a screenshot of edgeone.ai.",
  "preset.skill.sandboxAlgorithms": "Calculate the first 20 Fibonacci numbers and provide the execution result.",

  // Tool indicators
  "tool.commands": "Commands",
  "tool.files": "Files",
  "tool.codeRunner": "Code Runner",
  "tool.browser": "Browser",

  // Skill indicators
  "skill.sandboxAlgorithms": "Sandbox Algorithms",

  // Debug panel
  "debug.title": "Trace",
  "debug.events": "events",
  "debug.clear": "Clear",
  "debug.empty": "Waiting for SSE events...",
  "debug.emptyHint": "After sending a message, all raw backend data will be displayed here.",

  // Status & errors
  "status.error": "Request failed. Please check if the backend service is running.",
  "status.stopped": "⏹ *Generation stopped*",
  "status.backendError": "Backend abort request failed. The server may still be running.",

  // Language toggle
  "lang.switch": "中文",

  // Sidebar
  "sidebar.label": "Conversation list",
  "sidebar.title": "Chats",
  "sidebar.newChat": "New chat",
  "sidebar.loading": "Loading conversations...",
  "sidebar.loadMore": "Load more",
  "sidebar.loadingMore": "Loading...",
  "sidebar.emptyTitle": "No conversations yet",
  "sidebar.emptyHint": "Click \"New chat\" to start your first conversation.",
  "sidebar.delete": "Delete conversation",
  "sidebar.deleteConfirm": "Permanently delete this conversation? This cannot be undone.",

  // Aria labels (button hover/screen-reader)
  "aria.send": "Send",
  "aria.clearHistory": "Clear history",
  "aria.stopGeneration": "Stop generation",
} as const;

export default en;
