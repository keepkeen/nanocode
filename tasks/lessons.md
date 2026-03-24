# Lessons

- Keep project work inside `/Users/liuliming/code/My_agent`; the git root is `/Users/liuliming`, so repo-wide commands must be scoped carefully to avoid unrelated noise.
- Existing prototype packages are independently runnable but not workspace-integrated; root-level packaging and shared config must be established before higher-level validation is meaningful.
- When evolving SQLite schema, add forward migration logic and a smoke check against an existing local database, not only fresh test databases.
- When the user asks for a complete protocol implementation, do not silently narrow it to a robust subset; align scope to the full protocol surface or explicitly surface the boundary before coding.
- Async MCP changes need real process-level CLI smoke, not only in-process tests; cross-thread store writes and SIGINT shutdown bugs only surfaced when `nanocli mcp serve` and `nanocli mcp ping` ran as separate processes.
- When the user asks for Codex CLI / Claude Code style UX, do not stop at “persistent REPL”; implement the native onboarding habits too: model picker, API-key setup path, slash-command control surface, and visible agent activity during each turn.
