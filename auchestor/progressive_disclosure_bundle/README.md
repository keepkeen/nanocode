# Progressive Disclosure Agent Bundle

This bundle contains:

- `RESEARCH_REPORT.md`: a current research report (frozen on 2026-03-23, America/Los_Angeles)
- `src/progressive_disclosure/`: a production-oriented Python package for adaptive progressive disclosure in agents
- `tests/`: pytest coverage for the core behavior
- `examples/demo.py`: a runnable example showing how the disclosure layer can be embedded into an agent harness

## What the code implements

The package turns raw agent events into user-facing disclosures that are:

1. **Layered**: acknowledgement → plan → step → evidence → deep trace
2. **Adaptive**: disclosure changes with risk, confidence, audience, and event type
3. **Rate-limited**: avoids noisy updates through novelty and timing gates
4. **Approval-aware**: automatically escalates before risky or irreversible actions
5. **Evidence-backed**: can surface plan references, verification evidence, and trace fragments on demand

## Quick start

```bash
python examples/demo.py
```

Or install editable first:

```bash
pip install -e .
```

Run tests:

```bash
pytest
```

## Package layout

```text
src/progressive_disclosure/
├── __init__.py
├── abstractions.py
├── domain.py
├── engine.py
├── events.py
├── novelty.py
├── policies.py
├── providers.py
├── renderers.py
└── sinks.py
```

## Integration model

The intended integration point is a coding / browsing / workflow agent that already emits lifecycle events such as:

- task started
- plan created or updated
- action started
- action completed
- approval required
- error
- stalled
- task completed

The disclosure layer stays decoupled from the model, tool stack, and runtime. It consumes typed events and typed state snapshots and produces messages that a TUI / chat UI / web UI can display.
