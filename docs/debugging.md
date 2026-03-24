# Debugging

Run with `--debug` to persist the following artifacts:

- provider request payloads
- provider responses
- memory export snapshots
- disclosure messages
- tool audit ids and summaries
- session events and session transcripts
- subagent merge artifacts when delegation is enabled

Useful commands:

```bash
nanocli run "..." --debug
nanocli chat start "..." --debug
nanocli trace list
nanocli trace show <run-id>
nanocli trace tail
nanocli memory show
nanocli subagents inspect <run-id>
nanocli tui
```

Trace payloads live under the `artifacts/` directory inside the configured data dir. Sensitive headers and API keys are redacted before persistence.

## What to inspect first

- Wrong prompt assembly: inspect `provider_request` artifacts and the `diagnostics.context` / `diagnostics.retrieval` sections.
- Wrong memory hit: inspect `memory show`, then compare `events` and `blocks` against the current query.
- Tool issues: inspect `tool` traces and `.nanocli/tool_audit/<run-id>.jsonl`.
- Session issues: inspect `chat show <session-id>` and the TUI transcript pane.
- Delegation issues: inspect `subagents inspect <run-id>` and the saved `subagents.json` artifact.
