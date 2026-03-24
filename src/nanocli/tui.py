from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, ListItem, ListView, Static

from .runtime import AgentRuntime


class NanocliInspectorApp(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }

    #main {
        height: 1fr;
    }

    #sessions {
        width: 28%;
        border: round $accent;
    }

    #runs {
        width: 28%;
        border: round $accent;
    }

    .panel {
        border: round $accent;
        padding: 1;
    }

    #summary {
        height: 8;
    }

    #plan {
        height: 8;
    }

    #transcript {
        height: 12;
    }

    #memory {
        height: 8;
    }

    #mcp {
        height: 10;
    }

    #trace {
        height: 1fr;
    }
    """

    BINDINGS = [("q", "quit", "Quit"), ("r", "reload", "Reload")]

    def __init__(self, runtime: AgentRuntime, run_id: str | None = None, session_id: str | None = None) -> None:
        super().__init__()
        self.runtime = runtime
        self.initial_run_id = run_id
        self.initial_session_id = session_id
        self.session_ids: list[str] = []
        self.run_ids: list[str] = []
        self.selected_session_id: str | None = session_id
        self.selected_run_id: str | None = run_id

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical():
                yield ListView(id="sessions")
                yield ListView(id="runs")
            with Vertical():
                yield Static("No item selected.", id="summary", classes="panel")
                yield Static("Plan will appear here.", id="plan", classes="panel")
                yield Static("Transcript will appear here.", id="transcript", classes="panel")
                yield Static("Memory/execution state will appear here.", id="memory", classes="panel")
                yield Static("MCP activity will appear here.", id="mcp", classes="panel")
                yield Static("Trace timeline will appear here.", id="trace", classes="panel")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(self.runtime.config.chat.refresh_interval_ms / 1000.0, self._refresh_views)
        self._refresh_views()

    def action_reload(self) -> None:
        self._refresh_views()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "sessions":
            index = event.list_view.index or 0
            if self.session_ids:
                self.selected_session_id = self.session_ids[index]
                self._show_session(self.selected_session_id)
        if event.list_view.id == "runs":
            index = event.list_view.index or 0
            if self.run_ids:
                self.selected_run_id = self.run_ids[index]
                self._show_run(self.selected_run_id)

    def _refresh_views(self) -> None:
        self._load_sessions()
        self._load_runs()
        if self.selected_session_id:
            self._show_session(self.selected_session_id)
        elif self.selected_run_id:
            self._show_run(self.selected_run_id)
        elif self.session_ids:
            self.selected_session_id = self.session_ids[0]
            self._show_session(self.selected_session_id)
        elif self.run_ids:
            self.selected_run_id = self.run_ids[0]
            self._show_run(self.selected_run_id)

    def _load_sessions(self) -> None:
        list_view = self.query_one("#sessions", ListView)
        list_view.clear()
        self.session_ids = []
        sessions = self.runtime.list_sessions(limit=20)
        for item in sessions:
            label = f"{item.session_id[:8]}  {item.profile:<10}  {item.status:<8}  {item.title[:42]}"
            list_view.append(ListItem(Static(label)))
            self.session_ids.append(item.session_id)
        if self.initial_session_id and self.initial_session_id in self.session_ids:
            list_view.index = self.session_ids.index(self.initial_session_id)
            self.selected_session_id = self.initial_session_id
            self.initial_session_id = None

    def _load_runs(self) -> None:
        list_view = self.query_one("#runs", ListView)
        list_view.clear()
        self.run_ids = []
        runs = self.runtime.list_runs(limit=20)
        for item in runs:
            label = f"{item.run_id[:8]}  {item.status.value:<9}  {item.profile:<10}  {item.objective[:42]}"
            list_view.append(ListItem(Static(label)))
            self.run_ids.append(item.run_id)
        if self.initial_run_id and self.initial_run_id in self.run_ids:
            list_view.index = self.run_ids.index(self.initial_run_id)
            self.selected_run_id = self.initial_run_id
            self.initial_run_id = None

    def _show_session(self, session_id: str) -> None:
        try:
            session = self.runtime.get_session(session_id)
        except KeyError:
            return
        messages = self.runtime.get_session_messages(session_id)
        events = self.runtime.get_session_events(session_id)
        try:
            plan_state = self.runtime.get_plan_state(session_id)
            plan_lines = [
                f"{todo.get('linked_step_id') or todo['todo_id']}: {todo['status']}  {todo['content']}"
                for todo in plan_state.get("todos", [])[:8]
            ]
        except KeyError:
            plan_lines = ["No planner state found."]
        memory_snapshot = self.runtime.read_session_memory_snapshot(session_id)
        execution_state = memory_snapshot.get("execution_state", {})
        candidates = self.runtime.list_project_memory_candidates(status="pending")[:4]
        mcp_sessions = self.runtime.list_mcp_sessions(limit=3)
        mcp_lines: list[str] = []
        if mcp_sessions:
            latest = mcp_sessions[0]
            mcp_lines.extend(
                [
                    f"server={latest['server_name']} transport={latest['transport']} status={latest['status']}",
                    f"protocol={latest['protocol_version']} session={latest['session_identifier'] or '-'}",
                ]
            )
            for item in self.runtime.list_mcp_messages(int(latest["mcp_session_id"]), limit=6)[-6:]:
                method = item["method"] or "-"
                mcp_lines.append(f"{item['direction']:<8} {item['message_type']:<11} {method}")
            for item in self.runtime.list_mcp_stream_events(int(latest["mcp_session_id"]), limit=4)[-4:]:
                mcp_lines.append(f"stream   {item['event_name']:<11} {json_safe(item['payload'])}")
        else:
            mcp_lines.append("No MCP activity recorded.")
        summary = "\n".join(
            [
                f"session_id: {session.session_id}",
                f"profile: {session.profile}",
                f"status: {session.status}",
                f"title: {session.title}",
                f"last_run_id: {session.last_run_id or '-'}",
                f"message_count: {len(messages)}",
            ]
        )
        transcript = "\n\n".join(f"[{message.role}] {message.content}" for message in messages[-20:]) or "No session messages yet."
        memory_lines = [
            f"execution.{key} = {json_safe(value)}"
            for key, value in execution_state.items()
        ]
        memory_lines.extend(
            f"{block['kind']}/{block['plane']}: {json_safe(block['text'])}"
            for block in memory_snapshot.get("blocks", [])[-6:]
        )
        if candidates:
            memory_lines.append("--- pending project candidates ---")
            memory_lines.extend(
                f"{item['candidate_id']} {item['kind']}: {json_safe(item['text'])}"
                for item in candidates
            )
        trace_lines = [
            f"{event['created_at'][:19]}  {event['name']:<20}  {json_safe(event['payload'])}"
            for event in events[-20:]
        ]
        self.query_one("#summary", Static).update(summary)
        self.query_one("#plan", Static).update("\n".join(plan_lines) or "No planner state found.")
        self.query_one("#transcript", Static).update(transcript)
        self.query_one("#memory", Static).update("\n".join(memory_lines) or "No memory state found.")
        self.query_one("#mcp", Static).update("\n".join(mcp_lines))
        self.query_one("#trace", Static).update("\n".join(trace_lines) or "No session events found.")

    def _show_run(self, run_id: str) -> None:
        try:
            run = self.runtime.get_run(run_id)
        except KeyError:
            return
        traces = self.runtime.get_traces(run_id)
        summary = "\n".join(
            [
                f"run_id: {run.run_id}",
                f"status: {run.status.value}",
                f"profile: {run.profile}",
                f"phase: {run.phase}",
                f"objective: {run.objective}",
                f"summary: {run.summary or '-'}",
                f"error: {run.error or '-'}",
            ]
        )
        transcript = "\n".join(
            trace.message for trace in traces if trace.kind.value in {"plan", "note", "disclosure"}
        ) or "No narrative trace records found."
        plan_lines = [
            trace.message for trace in traces if trace.kind.value == "plan"
        ] or ["No plan trace records found."]
        trace_lines = [
            f"{trace.timestamp.isoformat(timespec='seconds')}  {trace.kind.value:<16}  {trace.message}"
            for trace in traces[-20:]
        ]
        mcp_sessions = self.runtime.list_mcp_sessions(limit=4)
        mcp_text = "\n".join(
            f"{item['server_name']}  {item['transport']}  {item['status']}  {item['protocol_version']}"
            for item in mcp_sessions
        ) or "No MCP sessions recorded."
        self.query_one("#summary", Static).update(summary)
        self.query_one("#plan", Static).update("\n".join(plan_lines[:8]))
        self.query_one("#transcript", Static).update(transcript)
        self.query_one("#memory", Static).update("Select a session to inspect session memory and execution state.")
        self.query_one("#mcp", Static).update(mcp_text)
        self.query_one("#trace", Static).update("\n".join(trace_lines) or "No trace records found.")


def json_safe(payload: object) -> str:
    text = str(payload)
    return text if len(text) <= 120 else text[:117] + "..."
