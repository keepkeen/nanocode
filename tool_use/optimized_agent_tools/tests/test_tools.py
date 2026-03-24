from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from agent_tools import (
    AuditLogger,
    AgentSessionState,
    BudgetConfig,
    Decision,
    SearchFilterConfig,
    SearchResultFilter,
    SecurityPolicy,
    SecureBashTool,
    SecureWebFetchTool,
    SecureWebSearchTool,
    ToolContext,
)
from agent_tools.base import SearchProvider
from agent_tools.types import SearchHit


class FakeSearchProvider(SearchProvider):
    provider_name = "fake"

    def search(self, query: str, *, limit: int = 5, include_domains=None, exclude_domains=None):
        return [
            SearchHit(title="Sponsored Result", url="https://ads.example.com/promo?utm_source=x", snippet="promoted shopping deal", metadata={"sponsored": True}),
            SearchHit(title="OpenCode GitHub", url="https://github.com/anomalyco/opencode?utm_source=x", snippet="terminal coding agent repo"),
            SearchHit(title="OpenCode Docs", url="https://opencode.ai/docs/tools", snippet="websearch webfetch docs"),
            SearchHit(title="Duplicate Docs", url="https://opencode.ai/docs/tools?utm_campaign=x", snippet="websearch webfetch docs again"),
            SearchHit(title="Random Store", url="https://store.example.com/product/opencode", snippet="buy now best price"),
        ][:limit]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"""
        <html>
            <head><title>Hello</title></head>
            <body>
                <header class='site-header subscribe'>Subscribe now</header>
                <nav>navigation ignored</nav>
                <article>
                    <h1>Test Page</h1>
                    <p>alpha beta gamma</p>
                    <p>bash websearch webfetch policy engine sandbox audit provenance budget manager</p>
                    <p>this paragraph is relevant to optimized agent tools and should survive chunk ranking</p>
                </article>
                <footer>related posts and cookie banner</footer>
            </body>
        </html>
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.policy = SecurityPolicy(workspace_root=self.root, allow_private_network=True, require_url_provenance=True, allow_http_upgrade=False)
        self.audit = AuditLogger(self.root / "audit.jsonl")
        self.ctx = ToolContext(session_id="s1", cwd=self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_policy_denies_destructive_command(self):
        decision = self.policy.decide_bash("rm -rf /", cwd=self.root)
        self.assertEqual(decision.decision, Decision.DENY)

    def test_bash_runs_simple_command(self):
        tool = SecureBashTool(policy=self.policy, audit=self.audit)
        result = tool.invoke(self.ctx, command="python -c \"print('ok')\"", cwd=self.root, allow_ask=True)
        self.assertTrue(result.ok)
        self.assertIn("ok", result.data["run"]["stdout"])

    def test_search_filter_drops_ads_and_duplicates(self):
        filterer = SearchResultFilter(SearchFilterConfig(top_k=5))
        filtered, stats = filterer.filter(FakeSearchProvider().search("opencode"), query="opencode websearch", normalize_url=lambda url: (url, True))
        self.assertEqual(stats.dropped_ads, 1)
        self.assertEqual(stats.dropped_duplicates, 1)
        urls = [item.url for item in filtered]
        self.assertTrue(any("github.com/anomalyco/opencode" in url for url in urls))
        self.assertFalse(any("store.example.com" in url for url in urls))

    def test_search_registers_urls(self):
        tool = SecureWebSearchTool(policy=self.policy, provider=FakeSearchProvider(), audit=self.audit)
        state = AgentSessionState()
        result = tool.invoke(self.ctx, query="opencode websearch", session_state=state)
        self.assertTrue(result.ok)
        self.assertTrue(state.is_url_known("https://github.com/anomalyco/opencode"))
        self.assertEqual(result.data["filtering"]["dropped_ads"], 1)

    def test_fetch_requires_provenance(self):
        tool = SecureWebFetchTool(policy=self.policy, audit=self.audit)
        result = tool.invoke(self.ctx, url="https://example.com", session_state=AgentSessionState())
        self.assertFalse(result.ok)
        self.assertEqual(result.summary, "URL provenance check failed")

    def test_fetch_local_server_compresses_and_ranks(self):
        server = HTTPServer(("127.0.0.1", 0), _Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            state = AgentSessionState()
            tool = SecureWebFetchTool(policy=self.policy, audit=self.audit, budget=BudgetConfig(max_total_chars=1800, max_summary_chars=300, max_chars_per_chunk=300, max_chunks=2))
            url = f"http://127.0.0.1:{server.server_port}/"
            state.remember_urls([url])
            result = tool.invoke(self.ctx, url=url, query="bash websearch policy budget", session_state=state, allow_ask=True)
            self.assertTrue(result.ok)
            self.assertEqual(result.data["content"]["title"], "Hello")
            self.assertLessEqual(len(result.data["content"]["summary"]), 300)
            self.assertLessEqual(len(result.data["content"]["evidence_chunks"]), 2)
            combined = " ".join(chunk["text"] for chunk in result.data["content"]["evidence_chunks"])
            self.assertIn("policy engine", combined)
            self.assertNotIn("cookie banner", combined)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
