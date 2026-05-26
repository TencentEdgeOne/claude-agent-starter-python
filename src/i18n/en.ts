const en = {
  // Header
  "app.title": "Agent Chat",
  "app.subtitle": "Running on EdgeOne with sandbox tools, session memory & observability",

  // Empty state
  "empty.title": "Claude Agent Starter",
  "empty.hint": "I'm a Claude assistant running on EdgeOne. I can call sandbox tools, persist session memory, and help you with debugging, file management, code execution, and web browsing.",
  "empty.features": "Sandbox Tools · Store Memory · Observability",

  // Chat input
  "chat.placeholder": "Type a message...  ⏎ Send · Shift+⏎ Newline",
  "chat.hint": "Powered by Claude Agent SDK + EdgeOne Sandbox · Demo only",

  // Preset questions
  "preset.1": "Use terminal commands to check the current system time and OS version.",
  "preset.2": "Create /tmp/hello.txt with content \"Hello EdgeOne\", then read it back.",
  "preset.3": "Use Python to calculate and print the first 10 Fibonacci numbers.",
  "preset.4": "Visit https://edgeone.ai and summarize the page content.",
  "preset.5": "Review the chat handler code for potential issues",
  "preset.6": "Generate API documentation for all endpoints",

  // Tool indicators
  "tool.commands": "Commands",
  "tool.files": "Files",
  "tool.codeRunner": "Code Runner",
  "tool.browser": "Browser",

  // Status & errors
  "status.error": "Request failed. Please check if the backend service is running.",
  "status.stopped": "⏹ *Generation stopped*",
  "status.backendError": "Backend abort request failed. The server may still be running.",

  // Language toggle
  "lang.switch": "中文",
} as const;

export default en;
