from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from agent_tools import (
    AuditLogger,
    AgentSessionState,
    Decision,
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
            SearchHit(title="A", url="https://example.com/a", snippet="alpha"),
            SearchHit(title="B", url="https://example.com/b", snippet="beta"),
        ][:limit]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<html><head><title>Hello</title></head><body><h1>Test Page</h1><p>alpha beta gamma</p></body></html>"
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
        result = tool.invoke(self.ctx, command="python -c \"print('ok')\"", cwd=self.root)
        self.assertTrue(result.ok)
        self.assertIn("ok", result.data["run"]["stdout"])

    def test_search_registers_urls(self):
        tool = SecureWebSearchTool(policy=self.policy, provider=FakeSearchProvider(), audit=self.audit)
        state = AgentSessionState()
        result = tool.invoke(self.ctx, query="example", session_state=state)
        self.assertTrue(result.ok)
        self.assertTrue(state.is_url_known("https://example.com/a"))

    def test_fetch_requires_provenance(self):
        tool = SecureWebFetchTool(policy=self.policy, audit=self.audit)
        result = tool.invoke(self.ctx, url="https://example.com", session_state=AgentSessionState())
        self.assertFalse(result.ok)
        self.assertEqual(result.summary, "URL provenance check failed")

    def test_fetch_local_server(self):
        server = HTTPServer(("127.0.0.1", 0), _Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            state = AgentSessionState()
            tool = SecureWebFetchTool(policy=self.policy, audit=self.audit)
            url = f"http://127.0.0.1:{server.server_port}/"
            state.remember_urls([url])
            result = tool.invoke(self.ctx, url=url, session_state=state, allow_ask=True)
            self.assertTrue(result.ok)
            self.assertEqual(result.data["content"]["title"], "Hello")
            self.assertIn("alpha beta gamma", result.data["content"]["text"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
