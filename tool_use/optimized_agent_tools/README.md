# optimized-agent-tools

Policy-first Bash, WebSearch, and WebFetch components for coding agents.

## What changed in this optimized build

This version adds two production-critical layers that web agents usually miss:

1. **Search result filtering**: sponsored/ad result removal, duplicate collapsing, URL canonicalization, light quality scoring, and relevance pruning before URLs enter the session ledger.
2. **Context budget management**: fetched pages are converted into main-content text, chunked, query-ranked, and compressed into a bounded summary plus evidence chunks.

The result is that the agent sees **evidence objects** instead of raw SERP noise and full-page HTML.

## Design goals

1. **Policy before execution**: every tool call passes through a security policy that returns `allow`, `ask`, or `deny`.
2. **Bounded autonomy**: commands, HTTP responses, redirects, search fan-out, and repeated identical calls are budgeted.
3. **Provenance-preserving fetch**: `webfetch` only allows URLs that were either user supplied or previously discovered by `websearch`.
4. **Decoupled architecture**: tools depend on abstract base classes and a shared policy, audit, filtering, ranking, and session layer.
5. **Auditable behavior**: each call can be written to a hash-chained JSONL audit log.

## Package layout

- `agent_tools/base.py`: abstract interfaces
- `agent_tools/types.py`: core dataclasses and enums
- `agent_tools/policy.py`: policy engine
- `agent_tools/bash.py`: secure Bash tool
- `agent_tools/websearch.py`: pluggable web search providers and search tool
- `agent_tools/webfetch.py`: secure fetch tool with provenance checks and dynamic compression
- `agent_tools/search_filters.py`: ad filtering, dedupe, relevance scoring, and result quality scoring
- `agent_tools/content_pipeline.py`: main-content extraction, chunking, ranking, and context budgeting
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
- filters sponsored/ad-like results before they become evidence
- canonicalizes URLs and collapses duplicates
- scores results by light relevance and source quality
- records only filtered URLs into the session provenance ledger
- repeated identical searches trigger a review state

### WebFetch

- normalizes and validates URLs
- blocks credentials in URLs
- blocks private/internal hosts by default
- optionally upgrades HTTP to HTTPS
- enforces URL provenance checks
- limits redirects and response size
- reduces HTML to main visible content
- query-ranks chunks and applies a hard context budget
- returns `summary + evidence_chunks + filtering stats` instead of page dumps

## Quick start

```python
from pathlib import Path
from agent_tools import (
    AgentSessionState,
    AuditLogger,
    BudgetConfig,
    SearchFilterConfig,
    SearchResultFilter,
    SecurityPolicy,
    SecureBashTool,
    SecureWebFetchTool,
    SecureWebSearchTool,
    TavilySearchProvider,
    ToolContext,
)

root = Path.cwd()
policy = SecurityPolicy(workspace_root=root)
audit = AuditLogger(root / ".agent_audit.jsonl")
ctx = ToolContext(session_id="session-1", cwd=root)
state = AgentSessionState()

search = SecureWebSearchTool(
    policy=policy,
    provider=TavilySearchProvider(),
    audit=audit,
    result_filter=SearchResultFilter(SearchFilterConfig(top_k=6)),
)
fetch = SecureWebFetchTool(
    policy=policy,
    audit=audit,
    budget=BudgetConfig(max_total_chars=9000, max_summary_chars=1000, max_chars_per_chunk=1200, max_chunks=5),
)
bash = SecureBashTool(policy=policy, audit=audit)

search_result = search.invoke(ctx, query="OpenCode websearch webfetch docs", session_state=state)
first_url = search_result.data["results"][0]["url"]
fetch_result = fetch.invoke(ctx, url=first_url, query="webfetch provenance and filtering", session_state=state)
bash_result = bash.invoke(ctx, command="python -c \"print('hello')\"", cwd=root, allow_ask=True)
```

## Returned fetch shape

```json
{
  "content": {
    "url": "...",
    "final_url": "...",
    "title": "...",
    "summary": "...",
    "evidence_chunks": [
      {"text": "...", "score": 0.91, "query_hits": 5},
      {"text": "...", "score": 0.84, "query_hits": 4}
    ]
  },
  "filtering": {
    "raw_chars": 25142,
    "visible_chars": 10320,
    "dropped_boilerplate_blocks": 12,
    "dropped_low_relevance_chunks": 18
  },
  "budget": {
    "max_total_chars": 9000,
    "max_summary_chars": 1000,
    "max_chars_per_chunk": 1200,
    "max_chunks": 5
  }
}
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
