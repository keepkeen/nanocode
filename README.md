# nanocode

`nanocode` is a local coding-agent shell that turns the research prototypes in this repository into one installable product.

Primary command: `nanocode`
Compatibility alias: `nanocli`

Current v0.1 scope:

- unified `nanocode` CLI package
- local run/session/subagent store with SQLite + files
- composite memory OS with project/session/subagent namespaces, SQLite-backed events/blocks, and FTS retrieval
- explicit project memory sources, derived repo resources, and evidence-backed memory candidates
- persistent plan/todo state stored in `execution_state`
- model profile switching across OpenAI Responses, Anthropic Messages, and OpenAI-compatible providers
- persistent chat sessions and resumable REPL
- canonical `skill.py` loading, render/export/install commands, and runtime tool injection
- local subagent mesh for research/review/implementation delegation plus provider artifact export
- async MCP client sessions for stdio and Streamable HTTP, plus async stdio/HTTP demo server entrypoints
- trace/debug export for provider calls, memory assembly, disclosures, tool activity, and session events
- live TUI inspector for sessions and runs

## Install

```bash
python -m pip install "nanocode @ git+https://github.com/keepkeen/nanocode.git"
```

Isolated tool install:

```bash
uv tool install git+https://github.com/keepkeen/nanocode.git
```

All examples below work with `nanocode`. `nanocli` remains available as a compatible alias.

## Quick start

Start an interactive coding session directly:

```bash
nanocode
```

Inside the session, the first-run onboarding flow is:

```text
/models
/apikey set openai <your-key>
```

Start with an initial prompt:

```bash
nanocode "Implement a cache-safe planner"
```

Continue the most recent session in the current workspace:

```bash
nanocode --continue
```

Run one prompt and exit:

```bash
nanocode --print "Summarize the current repository and propose the next step"
```

Manage stored API keys without editing shell rc files:

```bash
nanocode apikey list
nanocode apikey set openai <your-key>
nanocode apikey set claude <your-key> --scope project
```

Create a config file at `~/.config/nanocli/config.toml` or `.nanocli/config.toml`:

```toml
default_profile = "openai"

[profiles.openai]
provider = "openai_responses"
model = "gpt-5.4"
api_key_env = "OPENAI_API_KEY"

[profiles.claude]
provider = "anthropic"
model = "claude-sonnet-4.6"
api_key_env = "ANTHROPIC_API_KEY"

[profiles.deepseek]
provider = "deepseek"
model = "deepseek-chat"
api_key_env = "DEEPSEEK_API_KEY"
base_url = "https://api.deepseek.com"
```

Run a task:

```bash
nanocode "Implement a cache-safe planner" --debug
```

Start a persistent chat session:

```bash
nanocode chat start "Research and implement a planner runtime" --skill travel-weather-briefing --subagents
nanocode chat resume <session-id>
```

Available REPL commands:

```text
/help
/session
/status
/models
/models set <profile>
/apikey
/apikey set <profile> [key] [global|project]
/activity on|off
/model <profile>
/resume <session|last>
/clear
/skills
/skills add <name>
/skills drop <name>
/subagents on|off
/permissions
/mcp
/todo
/done <step_id>
/block <step_id> [reason]
/replan
/compact [instructions]
/trace
/quit
```

Each turn now prints a compact activity timeline by default so model requests, tool calls, plan updates, and other agent actions are visible without opening the trace inspector.

Planner commands:

```bash
nanocli plan show <session-id>
nanocli plan replan <session-id>
nanocli plan export <session-id> --provider openai
nanocli plan export <session-id> --provider deepseek --profile deepseek
nanocli plan export <session-id> --provider glm --model glm-5
```

Inspect project memory:

```bash
nanocli memory show
nanocli memory sources
nanocli memory candidates
nanocli memory promote <candidate-id>
nanocli memory reject <candidate-id>
nanocli memory rebuild
```

Inspect configured models and stored API-key status:

```bash
nanocode models list
nanocode models current
nanocode apikey list
nanocode apikey clear openai
```

Render or install skills:

```bash
nanocli skills list
nanocli skills render --name travel-weather-briefing --target chatgpt --target deepseek
nanocli skills install travel-weather-briefing
```

Run local subagents directly:

```bash
nanocli subagents list
nanocli subagents run "Research and review an implementation plan for the runtime"
```

Inspect traces:

```bash
nanocli trace list
nanocli trace show <run-id>
nanocli trace tail
```

Inspect or render MCP integration:

```bash
nanocli mcp list
nanocli mcp ping <server>
nanocli mcp inspect <server>
nanocli mcp render <server> --provider deepseek
nanocli mcp serve --transport stdio
nanocli mcp serve --transport http --port 8765
```

Launch the TUI inspector:

```bash
nanocli tui
```

Run release validation:

```bash
nanocli release check
```

## Platform support

- macOS: supported
- Linux: supported
- Windows: supported through WSL2 only

## Docs

- [Architecture](docs/architecture.md)
- [Debugging](docs/debugging.md)

## Notes

- Project memory now has three layers: explicit project sources, derived repo resources, and promoted durable semantic blocks. Raw transcript, tool dumps, and planner cursor state stay out of project memory.
- MCP support targets the current official async protocol shape first, then falls back to older `2025-06-18` style servers when configured.
