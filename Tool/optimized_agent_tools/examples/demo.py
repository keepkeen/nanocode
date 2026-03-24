from __future__ import annotations

from pathlib import Path
import json

from agent_tools import (
    AgentSessionState,
    AuditLogger,
    SecurityPolicy,
    SecureBashTool,
    SecureWebFetchTool,
    SecureWebSearchTool,
    ToolContext,
)
from agent_tools.base import SearchProvider
from agent_tools.types import SearchHit


class DemoSearchProvider(SearchProvider):
    provider_name = "demo"

    def search(self, query: str, *, limit: int = 5, include_domains=None, exclude_domains=None):
        return [
            SearchHit(
                title="OpenAI Codex GitHub",
                url="https://github.com/openai/codex",
                snippet="Lightweight coding agent running in terminal.",
            ),
            SearchHit(
                title="OpenCode docs",
                url="https://opencode.ai/docs/",
                snippet="Open-source AI coding agent in the terminal.",
            ),
        ][:limit]


def main() -> None:
    root = Path.cwd()
    policy = SecurityPolicy(workspace_root=root)
    audit = AuditLogger(root / ".agent_audit.jsonl")
    ctx = ToolContext(session_id="demo-session", cwd=root)
    state = AgentSessionState()

    search_tool = SecureWebSearchTool(policy=policy, provider=DemoSearchProvider(), audit=audit)
    fetch_tool = SecureWebFetchTool(policy=policy, audit=audit)
    bash_tool = SecureBashTool(policy=policy, audit=audit)

    search_result = search_tool.invoke(ctx, query="coding agent", session_state=state)
    print("SEARCH:")
    print(json.dumps(search_result.data, ensure_ascii=False, indent=2))

    bash_result = bash_tool.invoke(ctx, command="python -c \"print('hello from bash tool')\"", cwd=root)
    print("\nBASH:")
    print(json.dumps(bash_result.data, ensure_ascii=False, indent=2))

    # For real fetching, pass user_supplied=True or fetch URLs returned by search.
    if search_result.data.get("results"):
        first_url = search_result.data["results"][0]["url"]
        print(f"\nKnown URL from search ledger: {first_url}")
        print("You can now call SecureWebFetchTool.invoke(..., url=first_url, session_state=state)")


if __name__ == "__main__":
    main()
