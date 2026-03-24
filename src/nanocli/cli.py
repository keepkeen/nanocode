from __future__ import annotations

from pathlib import Path
import json
import shlex
import shutil
import subprocess
import sys
from glob import glob

import typer
from rich.console import Console
from rich.json import JSON
from rich.prompt import Prompt
from rich.table import Table

from .mcp_client import call_server_tool, inspect_server, list_server_tools, ping_server, render_server_payload, serve_http, serve_stdio
from .runtime import AgentRuntime
from .tui import NanocliInspectorApp


app = typer.Typer(help="Local coding agent shell with memory OS and trace capture.", no_args_is_help=True)
chat_app = typer.Typer(help="Persistent session chat and REPL commands.", no_args_is_help=True)
plan_app = typer.Typer(help="Inspect and update persisted planner state.", no_args_is_help=True)
trace_app = typer.Typer(help="Inspect recorded run traces.", no_args_is_help=True)
memory_app = typer.Typer(help="Inspect persisted memory state.", no_args_is_help=True)
models_app = typer.Typer(help="Inspect configured model profiles.", no_args_is_help=True)
mcp_app = typer.Typer(help="Inspect configured MCP servers.", no_args_is_help=True)
skills_app = typer.Typer(help="Inspect and manage runtime skills.", no_args_is_help=True)
subagents_app = typer.Typer(help="Inspect and trigger local subagents.", no_args_is_help=True)
release_app = typer.Typer(help="Run release/build verification checks.", no_args_is_help=True)
app.add_typer(chat_app, name="chat")
app.add_typer(plan_app, name="plan")
app.add_typer(trace_app, name="trace")
app.add_typer(memory_app, name="memory")
app.add_typer(models_app, name="models")
app.add_typer(mcp_app, name="mcp")
app.add_typer(skills_app, name="skills")
app.add_typer(subagents_app, name="subagents")
app.add_typer(release_app, name="release")

console = Console()


def _runtime(config: Path | None = None) -> AgentRuntime:
    return AgentRuntime(config_path=config)


def _print_run_result(result) -> None:
    table = Table(title="nanocli run")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("run_id", result.summary.run_id)
    table.add_row("session_id", result.session_id or "-")
    table.add_row("status", result.summary.status.value)
    table.add_row("profile", result.summary.profile)
    table.add_row("phase", result.summary.phase)
    table.add_row("summary", result.summary.summary or "-")
    if result.subagent_summary is not None:
        table.add_row("subagents", ", ".join(result.subagent_summary.selected_agents) or "-")
    console.print(table)


def _print_chat_reply(result) -> None:
    console.print(f"[bold]session[/bold] {result.session_id}")
    console.print(result.summary.summary or "No summary returned.")


def _print_plan_state(runtime: AgentRuntime, session_id: str) -> None:
    state = runtime.get_plan_state(session_id)
    table = Table(title=f"Plan: {session_id}")
    table.add_column("step_id")
    table.add_column("status")
    table.add_column("content")
    for todo in state["todos"]:
        table.add_row(str(todo.get("linked_step_id") or todo["todo_id"]), str(todo["status"]), str(todo["content"]))
    console.print(table)


def _handle_chat_command(runtime: AgentRuntime, line: str, *, state: dict[str, object]) -> bool:
    raw = line.strip()
    if not raw.startswith("/"):
        return False
    parts = shlex.split(raw[1:])
    if not parts:
        return True
    command = parts[0]

    if command in {"quit", "exit"}:
        raise typer.Exit()
    if command == "session":
        session = runtime.get_session(str(state["session_id"]))
        console.print(f"{session.session_id}  {session.profile}  {session.status}  {session.title}")
        return True
    if command == "model":
        if len(parts) < 2:
            console.print("usage: /model <profile>")
            return True
        state["profile"] = parts[1]
        console.print(f"profile -> {parts[1]}")
        return True
    if command == "skills":
        if len(parts) == 1:
            active = state["skills"]
            console.print("active skills: " + (", ".join(active) if active else "(none)"))
            return True
        action = parts[1]
        if action == "add" and len(parts) >= 3:
            skills = list(state["skills"])
            if parts[2] not in skills:
                skills.append(parts[2])
            state["skills"] = skills
            console.print("active skills: " + ", ".join(skills))
            return True
        if action in {"drop", "rm", "remove"} and len(parts) >= 3:
            state["skills"] = [item for item in state["skills"] if item != parts[2]]
            console.print("active skills: " + (", ".join(state["skills"]) if state["skills"] else "(none)"))
            return True
        console.print("usage: /skills | /skills add <name> | /skills drop <name>")
        return True
    if command == "subagents":
        if len(parts) < 2:
            console.print(f"subagents -> {'on' if state['subagents'] else 'off'}")
            return True
        state["subagents"] = parts[1].lower() in {"on", "true", "1", "yes"}
        console.print(f"subagents -> {'on' if state['subagents'] else 'off'}")
        return True
    if command == "todo":
        _print_plan_state(runtime, str(state["session_id"]))
        return True
    if command == "done":
        if len(parts) < 2:
            console.print("usage: /done <step_id>")
            return True
        runtime.mark_step_done(str(state["session_id"]), parts[1])
        _print_plan_state(runtime, str(state["session_id"]))
        return True
    if command == "block":
        if len(parts) < 2:
            console.print("usage: /block <step_id> [reason]")
            return True
        reason = " ".join(parts[2:]) if len(parts) > 2 else None
        runtime.mark_step_blocked(str(state["session_id"]), parts[1], reason)
        _print_plan_state(runtime, str(state["session_id"]))
        return True
    if command == "replan":
        runtime.replan_session(str(state["session_id"]))
        _print_plan_state(runtime, str(state["session_id"]))
        return True
    if command == "trace":
        session = runtime.get_session(str(state["session_id"]))
        if session.last_run_id:
            traces = runtime.get_traces(session.last_run_id)
            for trace in traces[-10:]:
                console.print(f"{trace.timestamp.isoformat(timespec='seconds')}  {trace.kind.value:<16}  {trace.message}")
        else:
            console.print("no completed run yet")
        return True
    console.print("commands: /session, /model <profile>, /skills, /skills add <name>, /skills drop <name>, /subagents on|off, /todo, /done <step_id>, /block <step_id> [reason], /replan, /trace, /quit")
    return True


@app.command()
def run(
    objective: str = typer.Argument(..., help="User task or coding objective."),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Profile name from config."),
    debug: bool = typer.Option(False, "--debug", help="Persist extra debug artifacts."),
    execute: bool = typer.Option(True, "--execute/--no-execute", help="Call the remote model provider."),
    allow_web: bool = typer.Option(False, "--allow-web", help="Enable web tools when API keys are present."),
    skill: list[str] = typer.Option(None, "--skill", help="Enable one or more runtime skills for this run."),
    use_subagents: bool = typer.Option(False, "--subagents", help="Enable local subagent delegation for this run."),
    config: Path | None = typer.Option(None, "--config", help="Explicit config file path."),
) -> None:
    runtime = _runtime(config)
    result = runtime.run(
        objective,
        profile_name=profile,
        debug=debug,
        execute=execute,
        allow_web=allow_web,
        selected_skills=skill or None,
        use_subagents=use_subagents,
    )
    _print_run_result(result)
    if result.provider_request is not None and debug:
        console.print(JSON.from_data(result.provider_request))
    if result.provider_response is not None:
        console.print("\n[bold]Provider Response[/bold]")
        console.print(JSON.from_data(result.provider_response))


@chat_app.command("start")
def chat_start(
    prompt: str | None = typer.Argument(None, help="Optional first-turn prompt."),
    profile: str | None = typer.Option(None, "--profile", "-p"),
    debug: bool = typer.Option(False, "--debug"),
    execute: bool = typer.Option(True, "--execute/--no-execute"),
    allow_web: bool = typer.Option(False, "--allow-web"),
    skill: list[str] = typer.Option(None, "--skill"),
    use_subagents: bool = typer.Option(False, "--subagents"),
    one_shot: bool = typer.Option(False, "--one-shot", help="Send the initial prompt and exit."),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    state: dict[str, object] = {
        "session_id": None,
        "profile": profile,
        "skills": skill or [],
        "subagents": use_subagents,
    }

    if prompt is not None:
        result = runtime.chat_turn(
            prompt,
            session_id=None,
            profile_name=profile,
            debug=debug,
            execute=execute,
            allow_web=allow_web,
            selected_skills=list(state["skills"]),
            use_subagents=bool(state["subagents"]),
        )
        state["session_id"] = result.session_id
        state["profile"] = result.summary.profile
        _print_chat_reply(result)
        if one_shot:
            return
    else:
        created = runtime.create_session(profile_name=profile or runtime.config.chat.default_repl_profile or runtime.config.default_profile)
        state["session_id"] = created.session_id
        state["profile"] = created.profile

    console.print(f"session {state['session_id']}  profile={state['profile']}")
    while True:
        line = Prompt.ask("user")
        if not line.strip():
            continue
        if _handle_chat_command(runtime, line, state=state):
            continue
        result = runtime.chat_turn(
            line,
            session_id=str(state["session_id"]),
            profile_name=str(state["profile"]) if state["profile"] else None,
            debug=debug,
            execute=execute,
            allow_web=allow_web,
            selected_skills=list(state["skills"]),
            use_subagents=bool(state["subagents"]),
        )
        _print_chat_reply(result)


@chat_app.command("resume")
def chat_resume(
    session_id: str = typer.Argument(...),
    prompt: str | None = typer.Argument(None),
    debug: bool = typer.Option(False, "--debug"),
    execute: bool = typer.Option(True, "--execute/--no-execute"),
    allow_web: bool = typer.Option(False, "--allow-web"),
    skill: list[str] = typer.Option(None, "--skill"),
    use_subagents: bool = typer.Option(False, "--subagents"),
    one_shot: bool = typer.Option(False, "--one-shot"),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    session = runtime.get_session(session_id)
    state: dict[str, object] = {
        "session_id": session_id,
        "profile": session.profile,
        "skills": skill or [],
        "subagents": use_subagents,
    }
    if prompt is not None:
        result = runtime.chat_turn(
            prompt,
            session_id=session_id,
            profile_name=session.profile,
            debug=debug,
            execute=execute,
            allow_web=allow_web,
            selected_skills=list(state["skills"]),
            use_subagents=bool(state["subagents"]),
        )
        _print_chat_reply(result)
        if one_shot:
            return

    console.print(f"session {session_id}  profile={session.profile}  title={session.title}")
    while True:
        line = Prompt.ask("user")
        if not line.strip():
            continue
        if _handle_chat_command(runtime, line, state=state):
            continue
        result = runtime.chat_turn(
            line,
            session_id=session_id,
            profile_name=str(state["profile"]),
            debug=debug,
            execute=execute,
            allow_web=allow_web,
            selected_skills=list(state["skills"]),
            use_subagents=bool(state["subagents"]),
        )
        _print_chat_reply(result)


@chat_app.command("list")
def chat_list(
    limit: int = typer.Option(20, "--limit", min=1, max=200),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    table = Table(title="Sessions")
    table.add_column("session_id")
    table.add_column("profile")
    table.add_column("status")
    table.add_column("title")
    table.add_column("last_run_id")
    for session in runtime.list_sessions(limit=limit):
        table.add_row(session.session_id, session.profile, session.status, session.title, session.last_run_id or "-")
    console.print(table)


@chat_app.command("show")
def chat_show(
    session_id: str = typer.Argument(...),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    session = runtime.get_session(session_id)
    messages = runtime.get_session_messages(session_id)
    console.print(f"{session.session_id}  {session.profile}  {session.status}  {session.title}")
    for message in messages:
        console.print(f"[{message.role}] {message.content}")


@app.command()
def tui(
    run_id: str | None = typer.Option(None, "--run-id", help="Optional run id to focus."),
    session_id: str | None = typer.Option(None, "--session-id", help="Optional session id to focus."),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    NanocliInspectorApp(runtime, run_id=run_id, session_id=session_id).run()


@trace_app.command("list")
def trace_list(
    limit: int = typer.Option(20, "--limit", min=1, max=200),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    table = Table(title="Recorded Runs")
    table.add_column("run_id")
    table.add_column("status")
    table.add_column("profile")
    table.add_column("phase")
    table.add_column("objective")
    for item in runtime.list_runs(limit=limit):
        table.add_row(item.run_id, item.status.value, item.profile, item.phase, item.objective)
    console.print(table)


@trace_app.command("show")
def trace_show(
    run_id: str = typer.Argument(...),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    traces = runtime.get_traces(run_id)
    table = Table(title=f"Trace: {run_id}")
    table.add_column("id")
    table.add_column("time")
    table.add_column("kind")
    table.add_column("message")
    table.add_column("artifact")
    for trace in traces:
        table.add_row(str(trace.trace_id), trace.timestamp.isoformat(timespec="seconds"), trace.kind.value, trace.message, trace.artifact_path or "-")
    console.print(table)


@trace_app.command("tail")
def trace_tail(
    run_id: str | None = typer.Option(None, "--run-id"),
    limit: int = typer.Option(10, "--limit", min=1, max=100),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    target_run_id = run_id or runtime.list_runs(limit=1)[0].run_id
    for trace in runtime.get_traces(target_run_id)[-limit:]:
        console.print(f"{trace.timestamp.isoformat(timespec='seconds')}  {trace.kind.value:<16}  {trace.message}")


@plan_app.command("show")
def plan_show(
    session_id: str = typer.Argument(...),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    _print_plan_state(runtime, session_id)


@plan_app.command("replan")
def plan_replan(
    session_id: str = typer.Argument(...),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    runtime.replan_session(session_id)
    _print_plan_state(runtime, session_id)


@plan_app.command("export")
def plan_export(
    session_id: str = typer.Argument(...),
    provider: str = typer.Option(..., "--provider"),
    profile: str | None = typer.Option(None, "--profile"),
    model: str | None = typer.Option(None, "--model"),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    payload = runtime.export_plan(session_id, provider=provider, profile_name=profile, model=model)
    if isinstance(payload, str):
        console.print(payload)
        return
    console.print(JSON.from_data(payload))


@memory_app.command("show")
def memory_show(
    session_id: str | None = typer.Option(None, "--session-id"),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    payload = runtime.read_session_memory_snapshot(session_id) if session_id else runtime.read_project_memory_snapshot()
    console.print(JSON.from_data(payload))


@memory_app.command("sources")
def memory_sources(
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    console.print(JSON.from_data(runtime.list_project_memory_sources()))


@memory_app.command("candidates")
def memory_candidates(
    status: str | None = typer.Option(None, "--status"),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    console.print(JSON.from_data(runtime.list_project_memory_candidates(status=status)))


@memory_app.command("promote")
def memory_promote(
    candidate_id: int = typer.Argument(...),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    console.print(JSON.from_data(runtime.promote_project_memory_candidate(candidate_id)))


@memory_app.command("reject")
def memory_reject(
    candidate_id: int = typer.Argument(...),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    console.print(JSON.from_data(runtime.reject_project_memory_candidate(candidate_id)))


@memory_app.command("rebuild")
def memory_rebuild(
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    console.print(JSON.from_data(runtime.rebuild_project_memory()))


@models_app.command("list")
def models_list(
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    table = Table(title="Profiles")
    table.add_column("name")
    table.add_column("provider")
    table.add_column("model")
    table.add_column("api_key_env")
    table.add_column("base_url")
    for profile in runtime.config.profiles.values():
        table.add_row(profile.name, profile.provider, profile.model, profile.api_key_env, profile.base_url or "-")
    console.print(table)


@mcp_app.command("list")
def mcp_list(
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    table = Table(title="Configured MCP Servers")
    table.add_column("name")
    table.add_column("transport")
    table.add_column("protocol")
    table.add_column("target")
    for server in runtime.config.mcp_servers.values():
        target = server.url or " ".join(server.command)
        table.add_row(server.name, server.transport, server.protocol_version, target)
    console.print(table)


@mcp_app.command("tools")
def mcp_tools(
    server_name: str = typer.Argument(...),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    if server_name not in runtime.config.mcp_servers:
        raise typer.BadParameter(f"Unknown MCP server: {server_name}")
    payload = list_server_tools(runtime.config.mcp_servers[server_name], manager=runtime.mcp)
    console.print(JSON.from_data(payload))


@mcp_app.command("ping")
def mcp_ping(
    server_name: str = typer.Argument(...),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    if server_name not in runtime.config.mcp_servers:
        raise typer.BadParameter(f"Unknown MCP server: {server_name}")
    payload = ping_server(runtime.config.mcp_servers[server_name], manager=runtime.mcp)
    console.print(JSON.from_data(payload))


@mcp_app.command("inspect")
def mcp_inspect(
    server_name: str = typer.Argument(...),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    if server_name not in runtime.config.mcp_servers:
        raise typer.BadParameter(f"Unknown MCP server: {server_name}")
    payload = inspect_server(runtime.config.mcp_servers[server_name], manager=runtime.mcp)
    console.print(JSON.from_data(payload))


@mcp_app.command("call")
def mcp_call(
    server_name: str = typer.Argument(...),
    tool_name: str = typer.Argument(...),
    arguments: str = typer.Option("{}", "--arguments", help="JSON object of tool arguments."),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    if server_name not in runtime.config.mcp_servers:
        raise typer.BadParameter(f"Unknown MCP server: {server_name}")
    payload = call_server_tool(runtime.config.mcp_servers[server_name], tool_name, json.loads(arguments), manager=runtime.mcp)
    console.print(JSON.from_data(payload))


@mcp_app.command("render")
def mcp_render(
    server_name: str = typer.Argument(...),
    provider: str = typer.Option(..., "--provider"),
    prompt: str = typer.Option("Inspect available MCP tools.", "--prompt"),
    model: str = typer.Option("gpt-5.4", "--model"),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    if server_name not in runtime.config.mcp_servers:
        raise typer.BadParameter(f"Unknown MCP server: {server_name}")
    payload = render_server_payload(
        runtime.config.mcp_servers[server_name],
        provider=provider,
        prompt=prompt,
        model=model,
        manager=runtime.mcp,
    )
    console.print(JSON.from_data(payload))


@mcp_app.command("serve")
def mcp_serve(
    transport: str = typer.Option("stdio", "--transport"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    server = runtime.build_mcp_server()
    if transport == "stdio":
        serve_stdio(server)
        return
    if transport == "http":
        serve_http(host=host, port=port, server=server)
        return
    raise typer.BadParameter(f"Unsupported MCP transport: {transport}")


@skills_app.command("list")
def skills_list(
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    table = Table(title="Skills")
    table.add_column("name")
    table.add_column("origin")
    table.add_column("tools")
    table.add_column("description")
    for skill in runtime.list_available_skills():
        table.add_row(skill.name, str(skill.metadata.get("origin", "-")), str(len(skill.tools)), skill.description)
    console.print(table)


@skills_app.command("render")
def skills_render(
    name: list[str] = typer.Option(None, "--name", help="Skill name to render; repeat for multiple."),
    target: list[str] = typer.Option(None, "--target", help="Render target; repeat for multiple."),
    out: Path | None = typer.Option(None, "--out"),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    written = runtime.render_skills(names=name or None, targets=target or None, out_dir=out)
    table = Table(title="Rendered Skill Artifacts")
    table.add_column("path")
    for path in written:
        table.add_row(str(path))
    console.print(table)


@skills_app.command("export")
def skills_export(
    name: list[str] = typer.Option(None, "--name"),
    target: list[str] = typer.Option(None, "--target"),
    out: Path = typer.Option(..., "--out"),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    written = runtime.render_skills(names=name or None, targets=target or None, out_dir=out)
    console.print(f"exported {len(written)} artifacts to {out}")


@skills_app.command("install")
def skills_install(
    source: str = typer.Argument(..., help="Builtin skill name or local skill package path."),
    destination: Path | None = typer.Option(None, "--destination"),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    target = runtime.install_skill(source, destination_root=destination)
    console.print(f"installed -> {target}")


@subagents_app.command("list")
def subagents_list(
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    table = Table(title="Subagents")
    table.add_column("name")
    table.add_column("description")
    table.add_column("capabilities")
    for agent in runtime.list_subagents():
        table.add_row(agent["name"], agent["description"], ", ".join(agent["capabilities"]))
    console.print(table)


@subagents_app.command("run")
def subagents_run(
    objective: str = typer.Argument(...),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    payload = runtime.run_subagents(objective)
    console.print(JSON.from_data(payload))


@subagents_app.command("inspect")
def subagents_inspect(
    run_id: str = typer.Argument(...),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    rows = runtime.list_subagent_runs(run_id)
    table = Table(title=f"Subagents: {run_id}")
    table.add_column("id")
    table.add_column("agent")
    table.add_column("status")
    table.add_column("namespace")
    table.add_column("summary")
    for row in rows:
        table.add_row(str(row["subagent_run_id"]), row["agent_name"], row["status"], row["namespace"], row["merged_summary"])
    console.print(table)


@subagents_app.command("export")
def subagents_export(
    run_id: str = typer.Argument(...),
    provider: str | None = typer.Option(None, "--provider"),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    runtime = _runtime(config)
    console.print(JSON.from_data(runtime.export_subagent_artifacts(run_id, provider=provider)))


@release_app.command("check")
def release_check(
    skip_tests: bool = typer.Option(False, "--skip-tests"),
    skip_build: bool = typer.Option(False, "--skip-build"),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    _ = config
    commands: list[tuple[str, list[str]]] = []
    commands.append(("import-package", [sys.executable, "-c", "import nanocli, nanocli.cli"]))
    if not skip_tests:
        commands.append(("pytest", [sys.executable, "-m", "pytest"]))
    if not skip_build:
        commands.append(("build", [sys.executable, "-m", "build", "--no-isolation"]))
    table = Table(title="Release Check")
    table.add_column("step")
    table.add_column("status")
    table.add_column("detail")
    for label, command in commands:
        proc = subprocess.run(command, cwd=Path.cwd(), capture_output=True, text=True, check=False)
        detail = (proc.stdout or proc.stderr).strip().splitlines()
        table.add_row(label, "ok" if proc.returncode == 0 else "failed", detail[-1] if detail else "-")
        if proc.returncode != 0:
            console.print(table)
            raise typer.Exit(proc.returncode)
    console_script = shutil.which("nanocode") or shutil.which("nanocli")
    sibling_dir = Path(sys.executable).resolve().parent
    sibling_script = sibling_dir / "nanocode"
    fallback_sibling_script = sibling_dir / "nanocli"
    argv_script = Path(sys.argv[0]).resolve()
    if not console_script and sibling_script.exists():
        console_script = str(sibling_script)
    if not console_script and fallback_sibling_script.exists():
        console_script = str(fallback_sibling_script)
    if not console_script and argv_script.exists() and argv_script.name in {"nanocode", "nanocli"}:
        console_script = str(argv_script)
    if not console_script:
        table.add_row("console-script", "failed", "nanocode/nanocli was not found on PATH or next to the active interpreter")
        console.print(table)
        raise typer.Exit(1)
    proc = subprocess.run([console_script, "--help"], cwd=Path.cwd(), capture_output=True, text=True, check=False)
    detail = (proc.stdout or proc.stderr).strip().splitlines()
    table.add_row("console-script", "ok" if proc.returncode == 0 else "failed", detail[0] if detail else "-")
    if proc.returncode != 0:
        console.print(table)
        raise typer.Exit(proc.returncode)
    if not skip_build:
        dist_files = sorted(glob("dist/*"))
        if not dist_files:
            table.add_row("twine", "failed", "dist/ is empty after build")
            console.print(table)
            raise typer.Exit(1)
        proc = subprocess.run([sys.executable, "-m", "twine", "check", *dist_files], cwd=Path.cwd(), capture_output=True, text=True, check=False)
        detail = (proc.stdout or proc.stderr).strip().splitlines()
        table.add_row("twine", "ok" if proc.returncode == 0 else "failed", detail[-1] if detail else "-")
        if proc.returncode != 0:
            console.print(table)
            raise typer.Exit(proc.returncode)
    console.print(table)


if __name__ == "__main__":
    app()
