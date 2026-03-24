# plan-todo-agent

A decoupled Python framework that combines:

- **Global Plan**: a dependency-aware execution graph for long-horizon work
- **Local Todo**: a user-visible progress list for the current wave of execution
- **Critic loop**: lightweight plan validation and replanning hooks
- **Provider adapters**: request/response shaping for OpenAI, DeepSeek, GLM, MiniMax, Kimi, Anthropic, and Claude Code renderers

## Why this design

Modern agent systems increasingly separate three concerns:

1. **reasoning / planning**
2. **tool orchestration**
3. **user-facing progress tracking**

This project encodes that separation explicitly so that you can:

- swap model vendors without rewriting core planning logic
- keep a stable internal schema for plans and todos
- render provider-specific payloads or config files from the same canonical state
- add skills without coupling them to a single SDK or agent harness

## Project layout

```text
plan_todo_agent/
  core/          # canonical schemas, interfaces, messages, utilities
  planning/      # dual-layer agent loop, critic, todo projection
  providers/     # vendor request/response adapters
  renderers/     # Claude Code and ChatGPT-oriented renderers
  skills/        # base skill contract + concrete example skill
  examples/      # runnable demos
```

## Quick start

```bash
cd plan_todo_agent
python -m plan_todo_agent.examples.demo_offline
python -m plan_todo_agent.examples.payload_showcase
```

## Design highlights

### 1) Canonical schema first
Internally, all providers map into the same schema:

- `Plan`
- `PlanStep`
- `TodoItem`
- `ToolSpec`
- `SkillContext`
- `AgentTurn`

### 2) Dual-layer Plan + Todo
The framework keeps a **global plan graph** and continuously projects the executable frontier into a **small todo list**.

This avoids two common failure modes:

- a giant static plan that becomes stale
- a flat todo list with no dependency structure

### 3) Critic before commit
A lightweight critic checks for:

- missing deliverables
- unresolved dependencies
- tool mismatch
- risk / rollback omissions

### 4) Provider-specific formatting at the boundary
The code keeps provider quirks isolated:

- OpenAI Responses API uses structured `input` items and `tools`
- DeepSeek / GLM / Kimi are treated as OpenAI-chat-like payloads
- Anthropic / MiniMax are treated as Messages-API-like payloads
- Claude Code is rendered as settings and subagent files, because it is a client/runtime rather than a model API

## Included example skill

`RepositoryRefactorSkill` demonstrates how a skill can provide:

- domain-specific objective shaping
- tool definitions
- skill-specific constraints
- success criteria

## Status

This repository is intentionally lightweight and framework-agnostic.
It focuses on **clean abstractions and provider adaptation**, not on shipping a full production runtime.
