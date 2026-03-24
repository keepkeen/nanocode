from __future__ import annotations

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


def main() -> None:
    root = Path.cwd()
    policy = SecurityPolicy(workspace_root=root)
    audit = AuditLogger(root / ".agent_audit.jsonl")
    ctx = ToolContext(session_id="demo-session", cwd=root)
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
        budget=BudgetConfig(max_total_chars=7000, max_summary_chars=900, max_chars_per_chunk=1000, max_chunks=4),
    )
    bash = SecureBashTool(policy=policy, audit=audit)

    result = search.invoke(ctx, query="OpenCode webfetch docs", session_state=state)
    print("search summary:", result.summary)
    for item in result.data.get("results", []):
        print("-", item["title"], item["url"])

    if result.data.get("results"):
        url = result.data["results"][0]["url"]
        fetched = fetch.invoke(ctx, url=url, query="webfetch provenance filtering", session_state=state)
        print("fetch summary:", fetched.summary)
        print(fetched.data["content"]["summary"])

    bash_result = bash.invoke(ctx, command="python -c \"print('hello from bash')\"", cwd=root, allow_ask=True)
    print("bash summary:", bash_result.summary)
    print(bash_result.data["run"]["stdout"])


if __name__ == "__main__":
    main()
