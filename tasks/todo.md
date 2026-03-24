# Nanocli Build Todo

- [x] Create a root Python package and release/install skeleton.
- [x] Add repository-local task tracking and lessons files.
- [x] Implement configuration loading and profile resolution.
- [x] Implement SQLite + filesystem run store for sessions, traces, and payload artifacts.
- [x] Integrate memory OS, planner bootstrap, disclosure engine, and provider request compilation.
- [x] Add CLI commands for run, chat, trace, memory, models, MCP, and TUI.
- [x] Add built-in local codebase tools with policy/audit hooks.
- [x] Add model-driven multi-round tool loop integration for supported provider families.
- [x] Persist structured memory snapshots, provider calls, tool calls, and disclosures in SQLite.
- [x] Load configured MCP tools into the runtime tool catalog.
- [x] Add tests for config, storage, runtime, and CLI wiring.
- [x] Add persistent chat sessions, REPL commands, and live session-aware TUI.
- [x] Replace JSON snapshot-only memory persistence with SQLite-native events/blocks and FTS-backed retrieval candidates.
- [x] Load provider-native skill packages into runtime and add skills CLI render/export/install commands.
- [x] Integrate parallel subagent mesh into runtime and expose inspection/trigger commands.
- [x] Add release-check command, CI workflows, packaging metadata, and optional live smoke tests.

## Current Execution Spec

- [x] Session runtime
  - [x] Persist sessions, messages, and session events in SQLite.
  - [x] Add resumable REPL chat flow with slash commands for session/model/skills/subagents/trace.
  - [x] Upgrade TUI to inspect live sessions as well as historical runs.
- [x] Memory OS storage
  - [x] Replace runtime memory hydration with SQLite-backed `events` and `blocks`.
  - [x] Add FTS-backed candidate retrieval and keep JSON snapshots as debug/export artifacts only.
  - [x] Mirror session/project memory into stable namespaces so resume works across runs.
- [x] Skills
  - [x] Load SKILL packages from project and user directories.
  - [x] Inject selected skill instructions and tools into runtime requests.
  - [x] Render/export provider-native artifacts to `.nanocli/generated/<provider>/`.
- [x] Subagents
  - [x] Add local worker mesh with `research`, `review`, and `implementation` specialists.
  - [x] Persist subagent traces and expose CLI inspection and manual trigger commands.
  - [x] Merge worker output into run/session summaries and debug traces.
- [x] Release and verification
  - [x] Add `release check` command and CI workflows for test/build/twine validation.
  - [x] Add offline tests for sessions, skills, subagents, and SQLite memory.
  - [x] Add optional env-gated live smoke tests for supported providers.

## Review

- The first integrated version favors a stable shell and observability over full autonomous coding.
- Tool execution now supports model-driven multi-round tool loops for the three provider families, with per-round request/response/tool traces.
- Packaging is now unified under one `nanocli` entrypoint instead of ad hoc subpackage execution.
- Session chat is now persistent and resumable, with SQLite transcript storage and a live inspector.
- Memory storage now uses SQLite-backed events/blocks plus FTS candidate retrieval; JSON snapshots remain export artifacts only.
- Skills now support discovery, install, runtime injection, and multi-provider render/export.
- Subagents now run through a local research/review/implementation mesh with merged traces.
- Release validation now includes `nanocli release check`, CI workflows, build/twine validation, and optional live smoke gating.
- Verification completed:
  - `pytest` -> `12 passed, 1 skipped`
  - `nanocli release check --skip-tests`
  - `nanocli chat --help`
  - `nanocli run "Research and implement a planner runtime" --no-execute --skill travel-weather-briefing --subagents`
  - `nanocli skills render --name travel-weather-briefing --target chatgpt`

## Alignment Repair Spec

- [x] Memory/runtime
  - [x] Split project/session/subagent namespaces so raw transcript and tool observations stay session-scoped.
  - [x] Move planner cursor/todo/current-step persistence into `execution_state` and stop writing `next step` into project memory.
  - [x] Compile provider requests from a composite memory view instead of mutating payloads after `prepare_request()`.
  - [x] Mirror tool observations into session memory, session transcript, and structured tool/provider traces.
- [x] Planner
  - [x] Persist `AgentState` per session and wire `bootstrap()` plus `apply_execution_feedback()` into chat/runtime.
  - [x] Add CLI and REPL plan controls: `plan show`, `plan replan`, `/todo`, `/done`, `/block`, `/replan`.
  - [x] Expose provider-facing plan exports using the original `plan_todo_agent` renderers/adapters.
- [x] Skills + subagents
  - [x] Make `skill.py` with exported `SKILL`/`SKILLS` the canonical executable skill format.
  - [x] Keep `SKILL.md` packages as instruction-only fallback and render/export artifacts.
  - [x] Persist subagent runs/results/provider artifacts and expose `subagents export`.
- [x] MCP + tools
  - [x] Replace one-shot MCP calls with a stateful client that performs `initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`.
  - [x] Add `nanocli mcp ping`, `nanocli mcp serve`, and `nanocli mcp render`.
  - [x] Remove the forced `user_supplied=True` web fetch path and keep provider/tool provenance attached to the active session/run.
- [x] Docs + verification
  - [x] Update CLI/TUI/docs/CI to reflect WSL2-only Windows support and the repaired architecture.
  - [x] Expand tests for session isolation, planner persistence, canonical skills, MCP handshake/rendering, and subagent artifacts.
  - [x] Run `pytest`, smoke CLI commands, and release validation after the refactor.

## Alignment Review

- Runtime now compiles provider requests from a composite project/session memory view and no longer mutates prompts after memory compilation.
- Planner state now persists in SQLite `execution_state`, with session-facing CLI and REPL commands for todo management and replanning.
- Canonical executable skills now load from `skill.py`; markdown-only skills remain instruction-only bundles instead of fake executable packages.
- Subagent runs now persist working memory, per-agent results, and provider-facing artifacts for export/debug workflows.
- MCP stdio/http sessions are stateful, follow the expected handshake, and support render/ping/call/serve flows.
- CLI, TUI, docs, and CI now reflect the repaired architecture and the WSL2-only Windows boundary.

- Verification completed:
  - `pytest` -> `16 passed, 1 skipped`
  - `nanocli plan --help`
  - `nanocli mcp --help`
  - `nanocli run "Alignment repair smoke" --no-execute --skill travel-weather-briefing --subagents`
  - `nanocli release check --skip-tests`

## Async MCP + Project Memory

- [x] Schema + config
  - [x] Extend config/models for async MCP protocol settings, auth headers, protocol version fallback, and project memory source/promotion policies.
  - [x] Add SQLite tables and migration helpers for MCP sessions/messages/capabilities/auth state plus memory candidates/sources/derived project resources.
  - [x] Fix planner export profile/model resolution so provider names are never used as model ids.
- [x] Async MCP runtime
  - [x] Replace the sync line-based MCP helper with an async session manager that supports stdio, Streamable HTTP, and legacy SSE fallback.
  - [x] Implement lifecycle, progress, cancel, logging, tools, resources, prompts, completion, roots, sampling, elicitation, and tasks capability handling.
  - [x] Upgrade `nanocli mcp serve` to a real async MCP server over stdio and optional HTTP.
- [x] Project memory
  - [x] Add explicit project memory sources from `AGENTS.md`, `CLAUDE.md`, `.nanocli/project.md`, and `.nanocli/memory/**/*.md`.
  - [x] Add derived project resources (`repo_map`, `repo_overview`) without mixing them into durable semantic memory.
  - [x] Add hybrid promotion with evidence-backed candidates, manual promote/reject controls, and keep execution state out of project memory.
- [x] CLI/TUI/docs
  - [x] Add `memory candidates/promote/reject/rebuild/sources` and richer MCP inspection/serve flows.
  - [x] Surface MCP state, approvals, and project memory diagnostics in the TUI and debug traces.
  - [x] Update README, architecture docs, and lessons to reflect the full async MCP architecture and new memory model.
- [x] Verification
  - [x] Add unit/integration coverage for async stdio/SHTTP MCP, protocol fallback, sampling/elicitation/roots, project memory candidates, and explicit sources.
  - [x] Run `pytest`, MCP smoke flows, CLI smoke flows, and release validation after implementation.

## Async MCP + Project Memory Review

- `nanocli` now keeps explicit project memory sources, derived repo resources, and evidence-backed memory candidates separate from session transcript and `execution_state`.
- Planner export now resolves provider-specific models from real profiles or explicit `--model` overrides instead of leaking provider names into request payloads.
- MCP moved to a background async session actor with config-signature session caching, stdio subprocess readers, HTTP JSON/SSE handling, session tracing, and async stdio/HTTP serve entrypoints.
- CLI and TUI now expose project memory candidate management and MCP inspection instead of hiding those states behind internal traces only.
- Verification completed:
  - `.venv/bin/pytest` -> `17 passed, 2 skipped`
  - `.venv/bin/nanocli memory --help`
  - `.venv/bin/nanocli mcp --help`
  - `.venv/bin/nanocli plan --help`
  - `.venv/bin/nanocli release check --skip-tests`

## CLI MCP Bugfix Validation

- [x] Reproduce async MCP ledger writes through the real CLI against a live HTTP MCP server.
- [x] Fix cross-thread SQLite access in MCP session/message persistence.
- [x] Add regression coverage for runtime-backed HTTP MCP inspection and persisted MCP ledger rows.
- [x] Reproduce `nanocli mcp serve --transport http` shutdown issues after a real request and fix graceful SIGINT cleanup.
- [x] Re-run full pytest, release validation, CLI MCP smoke, and CLI memory smoke after the fixes.

## CLI MCP Bugfix Review

- Real CLI MCP smoke exposed a background-thread SQLite bug that in-process manager tests missed; `LocalStateStore` now uses a serialized cross-thread SQLite connection wrapper.
- Real terminal shutdown smoke also exposed an HTTP server shutdown bug after handled requests; `serve_http()` now uses an explicit stop event and fast site shutdown instead of relying on `asyncio.run()` cancellation.
- MCP regression coverage now verifies runtime-backed HTTP session persistence and clean signal-based shutdown after a real ping.
- Additional CLI memory smoke confirmed evidence-backed promotion still works end-to-end with isolated XDG state directories.
- Verification completed:
  - `.venv/bin/pytest` -> `19 passed, 1 skipped`
  - `.venv/bin/nanocli release check`
  - `.venv/bin/nanocli mcp ping demo_http --config /var/folders/g6/t54w_fkj7jxc97810f5tjvkr0000gn/T/tmp.9VFlXGf76g/config.toml`
  - `.venv/bin/nanocli mcp inspect demo_http --config /var/folders/g6/t54w_fkj7jxc97810f5tjvkr0000gn/T/tmp.9VFlXGf76g/config.toml`
  - `.venv/bin/nanocli mcp render demo_http --provider deepseek --model deepseek-chat --config /var/folders/g6/t54w_fkj7jxc97810f5tjvkr0000gn/T/tmp.9VFlXGf76g/config.toml`
  - `XDG_CONFIG_HOME=/var/folders/g6/t54w_fkj7jxc97810f5tjvkr0000gn/T/tmp.AonwTlnetK XDG_DATA_HOME=/var/folders/g6/t54w_fkj7jxc97810f5tjvkr0000gn/T/tmp.JPbYG3H49b .venv/bin/nanocli chat start "Remember that I prefer concise typed Python." --no-execute --one-shot`
  - `XDG_CONFIG_HOME=/var/folders/g6/t54w_fkj7jxc97810f5tjvkr0000gn/T/tmp.AonwTlnetK XDG_DATA_HOME=/var/folders/g6/t54w_fkj7jxc97810f5tjvkr0000gn/T/tmp.JPbYG3H49b .venv/bin/nanocli memory candidates`

## Strict Prototype Alignment

- [x] Replace the demo runtime tool registry with a session-aware executor that preserves URL provenance, repeated-call state, and audit semantics from `optimized_agent_tools`.
- [x] Make `tools.web_search_provider` real and route Tavily/Brave/Exa through the configured provider instead of hardcoding Tavily.
- [x] Integrate MCP server selection into main provider request compilation with `auto|native|flatten|proxy` behavior.
- [x] Stop auto-flattening every MCP server into local proxy tools; keep proxy tools only for fallback/debug or explicit `proxy` mode.
- [x] Replace the default demo `mcp serve` surface with a runtime-backed MCP server exposing workspace tools, prompts, memory resources, and traces.
- [x] Persist explicit project sources as stable control-plane blocks and persist the tool manifest as durable control-plane state.
- [x] Expand hybrid memory promotion to use multi-source corroboration and tighten repo-derived resource filtering.
- [x] Decouple planner skill selection from the hardcoded `RepositoryRefactorSkill` runtime default.
- [x] Align skills defaults and artifact layout with the prototype outputs, including `claude-subagent`.
- [x] Keep subagent provider-artifact behavior provider-agnostic and add regression coverage for the repaired alignment paths.

## Strict Prototype Alignment Review

- Runtime tools now flow through a session-aware executor backed by `optimized_agent_tools`, so web provenance, repeated-call counts, and audit ids survive across the run instead of bypassing session state.
- MCP integration now resolves per-provider `auto|native|flatten|proxy` behavior in the main runtime, and `mcp serve` now defaults to a runtime-backed surface instead of the weather demo.
- Project sources and the stable tool manifest now materialize as control-plane blocks, while memory candidates can be corroborated by explicit sources and derived repo resources before promotion.
- Planner skill selection now comes from config, and skills default rendering now includes the prototype-compatible `claude-subagent` artifact path under `claude-code/`.
- Verification completed:
  - `.venv/bin/pytest -q` -> `23 passed, 1 skipped`
  - `.venv/bin/nanocli release check --skip-tests`
  - `XDG_CONFIG_HOME=/tmp/nanocli_cfg XDG_DATA_HOME=/tmp/nanocli_data .venv/bin/nanocli run "Strict alignment smoke" --no-execute`
  - `.venv/bin/nanocli skills render --name travel-weather-briefing --target claude-subagent --out /tmp/nanocli_skill_out`
  - Runtime-backed MCP HTTP smoke via `.venv/bin/nanocli mcp serve --transport http --port 8879` + `McpClientManager.ping/list_tools`

## Prototype Alignment Tail

- [x] Reconcile deleted or changed explicit project sources so stale source control blocks are deactivated instead of lingering in stable control.
- [x] Add deterministic typed source fragments for `Preference`, `Style`, `Constraint`, and `Decision` markers/headings while keeping whole-file source blocks canonical.
- [x] Unify MCP `auto|native|flatten|proxy` mode resolution across runtime and `nanocli mcp render`, and stop native render from depending on `tools/list`.
- [x] Add anthropic non-native MCP render fallback that emits standard tool payloads instead of hard-failing.
- [x] Extend runtime-backed MCP resources to always expose `latest_run`, `planner_current`, and `latest_traces`, even when empty.
- [x] Add regression tests for stale source cleanup, typed source fragments, native render without `tools/list`, anthropic flatten render, and runtime-backed trace resources.

## Prototype Alignment Tail Review

- Deleted project sources now reconcile against active control blocks, and stale `project_source:*` plus extracted fragment blocks are deactivated during rebuilds instead of lingering in stable control.
- Explicit project sources now yield deterministic typed fragments for `Preference`, `Style`, `Constraint`, and `Decision` markers/headings while retaining the whole-file source block as the canonical source-backed control record.
- MCP integration mode resolution now comes from one shared path for runtime and `nanocli mcp render`; native OpenAI/Anthropic render no longer depends on `tools/list`, and Anthropic non-native render falls back to standard `tools` payloads instead of failing.
- Runtime-backed MCP resources now always expose `workspace_root`, `project_memory`, `latest_run`, `planner_state`, and `latest_traces`, with empty-but-stable payloads when no run or planner state exists.
- Verification completed:
  - `.venv/bin/pytest -ra` -> `25 passed, 3 skipped`
  - `.venv/bin/nanocli release check --skip-tests`
  - `XDG_CONFIG_HOME=/tmp/nanocli_cfg XDG_DATA_HOME=/tmp/nanocli_data .venv/bin/nanocli run "Prototype alignment tail smoke" --no-execute`
  - `XDG_CONFIG_HOME=/tmp/nanocli_cfg XDG_DATA_HOME=/tmp/nanocli_data .venv/bin/nanocli memory rebuild`
  - `XDG_CONFIG_HOME=/tmp/nanocli_cfg XDG_DATA_HOME=/tmp/nanocli_data .venv/bin/nanocli memory show`
  - Escalated local loopback smoke: `.venv/bin/nanocli mcp serve --transport http --port 8891` plus `curl` `initialize`, `resources/list`, and `resources/read nanocli://traces/latest`

## GitHub Push + One-Line Install

- [ ] Initialize this directory as its own git repository instead of relying on the parent `~/` repo.
- [ ] Add ignore rules for runtime/build artifacts so only project files are pushed.
- [ ] Expose `nanocode` as the primary package and console-script while keeping `nanocli` as a compatibility alias.
- [ ] Document one-line install from `https://github.com/keepkeen/nanocode.git`.
- [ ] Verify local build/install from a git-backed source and push `main` to `keepkeen/nanocode.git`.

## GitHub Push + One-Line Install Review

- Pending implementation.
