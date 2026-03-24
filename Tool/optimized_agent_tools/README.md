# optimized-agent-tools

Policy-first Bash, WebSearch, and WebFetch components for coding agents.

## Design goals

1. **Policy before execution**: every tool call passes through a security policy that returns `allow`, `ask`, or `deny`.
2. **Bounded autonomy**: commands, HTTP responses, redirects, and repeated identical calls are budgeted.
3. **Provenance-preserving fetch**: `webfetch` only allows URLs that were either user supplied or previously discovered by `websearch`.
4. **Decoupled architecture**: tools depend on abstract base classes and a shared policy/audit/session layer.
5. **Auditable behavior**: each call can be written to a hash-chained JSONL audit log.

## Package layout

- `agent_tools/base.py`: abstract interfaces
- `agent_tools/types.py`: core dataclasses and enums
- `agent_tools/policy.py`: policy engine
- `agent_tools/bash.py`: secure Bash tool
- `agent_tools/websearch.py`: pluggable web search providers and search tool
- `agent_tools/webfetch.py`: secure fetch tool with provenance checks and text reduction
- `agent_tools/sandbox.py`: sandbox adapters (noop + firejail wrapper)
- `agent_tools/registry.py`: registry and session state
- `agent_tools/audit.py`: hash-chained JSONL audit logger
- `tests/`: unit tests
- `examples/demo.py`: small demo script

## Security model

### Bash

- denies destructive commands such as `rm -rf /`, privilege escalation, disk mutation, and privileged Docker usage
- asks for approval on chained shell commands, outbound interactive network commands, and remote writes
- sanitizes environment variables using an allowlist
- constrains working directory and writable roots
- caps output size and runtime
- supports an external sandbox adapter for OS-level isolation

### WebSearch

- provider abstraction for Brave, Tavily, or Exa
- domain filtering and URL policy checks on results
- deduplicates normalized URLs
- records discovered URLs into the session provenance ledger
- repeated identical searches trigger a review state

### WebFetch

- normalizes and validates URLs
- blocks credentials in URLs
- blocks private/internal hosts by default
- optionally upgrades HTTP to HTTPS
- enforces URL provenance checks
- limits redirects and response size
- reduces HTML to visible text and extracts query-relevant spans

## Quick start

```python
from pathlib import Path
from agent_tools import (
    AgentSessionState,
    AuditLogger,
    SecurityPolicy,
    SecureBashTool,
    SecureWebFetchTool,
    SecureWebSearchTool,
    ToolContext,
    TavilySearchProvider,
)

root = Path.cwd()
policy = SecurityPolicy(workspace_root=root)
audit = AuditLogger(root / ".agent_audit.jsonl")
ctx = ToolContext(session_id="session-1", cwd=root)
state = AgentSessionState()

search = SecureWebSearchTool(policy=policy, provider=TavilySearchProvider(), audit=audit)
fetch = SecureWebFetchTool(policy=policy, audit=audit)
bash = SecureBashTool(policy=policy, audit=audit)

search_result = search.invoke(ctx, query="OpenAI Codex GitHub", session_state=state)
first_url = search_result.data["results"][0]["url"]
fetch_result = fetch.invoke(ctx, url=first_url, query="Codex sandbox", session_state=state)
bash_result = bash.invoke(ctx, command="python -c \"print('hello')\"", cwd=root)
```

## Notes

- This package intentionally keeps the network stack lightweight and uses Python's standard library.
- For production use, prefer running Bash inside Docker, gVisor, Firecracker, or another OS-enforced sandbox.
- Search providers require API keys unless you supply your own provider implementation.

## Running tests

```bash
python -m unittest discover -s tests -v
```

## License

MIT
