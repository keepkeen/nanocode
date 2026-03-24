# Architecture

`nanocli` is organized as a thin product shell over the existing prototype packages in this repository.

## Core flow

1. CLI loads merged config from global and project config files.
2. Runtime opens the local SQLite state store and memory store, then creates a `run_id`.
3. If a session exists, the turn is attached to `session_id` and persisted in `sessions`, `session_messages`, and `session_events`.
4. Planner loads or bootstraps a persistent `AgentState`, stores it in `execution_state`, and projects the active todo frontier.
5. Memory runtime refreshes explicit project sources and derived repo resources, then composes `project + session + execution_state + recent turns + current turn` into a single provider request without post-compilation prompt mutation.
6. Optional skill controls and optional subagent outputs enter the compiler as control-plane messages before provider request assembly.
7. Provider request, context diagnostics, disclosures, tool activity, and session/subagent state are persisted as trace records.
8. If an API key is present and `--execute` is enabled, the runtime calls the selected provider.
9. TUI and trace commands inspect the stored session/run state instead of recomputing it.

## Major subsystems

- `nanocli.config`: profile/config merge and defaults
- `nanocli.storage`: SQLite schema, artifact persistence, session storage, and trace retrieval
- `nanocli.memory_runtime`: composite namespace compiler, explicit project-source loader, derived repo resources, and promotion rules
- `nanocli.sqlite_memory`: SQLite-backed memory events/blocks/FTS retrieval plus project sources/resources/candidates
- `nanocli.runtime`: run/session orchestration across plan, memory, skills, subagents, disclosure, and provider execution
- `nanocli.skills_runtime`: skill discovery, install/render/export, and runtime tool wrapping
- `nanocli.subagents_runtime`: local research/review/implementation mesh
- `nanocli.mcp_client`: stateful MCP client/session manager plus demo stdio server
- `nanocli.tools`: built-in repo tools and MCP helpers
- `nanocli.tui`: Textual inspector over persisted session and run state

## Memory layout

- Project namespace: `project:<cwd-hash>` stores durable control, explicit project sources, derived repo resources, and promoted semantic memory only.
- Session namespace: `session:<session-id>` stores transcript, tool observations, execution summaries, and retrieval-local memory.
- Subagent namespace: `subagent:<run-id>:<agent-name>` stores per-worker summaries and archived memory.
- SQLite tables: `events`, `blocks`, `block_refs`, `execution_state`, `fts_blocks`, `memory_sources`, `derived_project_resources`, and `memory_candidates` back retrieval, project context refresh, and promotion tracking.
- JSON snapshots: `.nanocli/project_memory.json` remains as an export/debug artifact, not the primary store.
- Explicit project sources come from `AGENTS.md`, `CLAUDE.md`, `.nanocli/project.md`, `.nanocli/memory/**/*.md`, and optional imports from `.continue/rules/**` and `.openhands/microagents/**`.
- Derived repo resources currently include `repo_map` and `repo_overview`; they are refreshable context artifacts, not durable semantic memory.
- Hybrid promotion only allows durable semantic kinds such as preferences, facts, constraints, decisions, and style blocks after corroborating evidence; execution state and raw transcript never auto-promote.

## Session and chat flow

- `nanocli chat start` creates a durable session.
- Each turn creates a new `run_id` linked to that session.
- User/assistant/tool messages are stored separately from memory blocks so transcript replay and memory retrieval stay decoupled.
- `execution_state` is the single durable source for planner state, current step, blocked steps, and todo frontier.
- The TUI can attach to both active sessions and historical runs.

## Skills and subagents

- Skills load from built-ins plus project/user skill directories.
- `skill.py` exporting `SKILL` or `SKILLS` is the executable truth for runtime skills.
- `SKILL.md`-only packages are treated as instruction-only bundles and are never mounted as executable tools.
- Canonical skill definitions can be rendered to ChatGPT, Claude Code, DeepSeek, GLM, Kimi, and MiniMax formats.
- Skill tools with local executors are mounted into the same tool registry used by the main runtime.
- Subagents are local asynchronous workers with independent routing and merge traces.
- Provider-facing subagent artifacts are persisted for OpenAI, Claude Code, DeepSeek, GLM, Kimi, and MiniMax exports.

## MCP and platform boundary

- MCP client sessions run through a background async session actor, cache by server config signature, and negotiate protocol/capabilities before handling requests.
- stdio transport keeps a long-lived subprocess with independent stdout/stderr readers and supports out-of-order responses plus mixed notifications.
- HTTP transport supports JSON responses, Streamable HTTP SSE responses, optional long-lived SSE stream attachment, `Mcp-Session-Id`, and protocol-version fallback.
- MCP ledger data is persisted in `mcp_sessions`, `mcp_messages`, `mcp_stream_events`, `mcp_capabilities`, and `mcp_auth_tokens`.
- `nanocli mcp serve` exposes the async demo MCP server over stdio or HTTP for smoke testing and adapter rendering.
- macOS and Linux are supported directly.
- Windows support is limited to WSL2.

## Reused prototypes

- `agent_memory_os`: event log, block derivation, retrieval, cache-safe compilation, provider request shaping
- `plan_todo_agent`: stable plan/todo bootstrap
- `progressive_disclosure`: user-facing progress messages
- `agent_tools`: secure bash/websearch/webfetch policy and audit primitives
- `mcp_polyglot`: MCP request and tool normalization helpers
- `multi_vendor_skills`: provider-native skill packaging and renderers
- `subagent_framework`: canonical subagent router/orchestrator abstractions
