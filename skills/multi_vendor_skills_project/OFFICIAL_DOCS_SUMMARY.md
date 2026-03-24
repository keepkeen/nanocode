# Official Docs Mapping Summary

This file records the format decisions behind the adapters.

## OpenAI / ChatGPT
- Publicly documented as "Skills in ChatGPT"
- OpenAI states skills follow the Agent Skills open standard
- Practical adapter choice: `SKILL.md` package

## Anthropic / Claude Code
- Anthropic publishes an official `anthropics/skills` repository and Agent Skills spec
- Claude Code also documents subagents as a reusable markdown + frontmatter format
- Practical adapter choice: `SKILL.md` package + optional subagent output

## DeepSeek
- Public official docs center on Function Calling
- Practical adapter choice: OpenAI-compatible `tools=[...]` rendering

## Zhipu GLM
- Public official docs center on 工具调用 / Function Calling and MCP
- Practical adapter choice: OpenAI-compatible `tools=[...]` rendering

## MiniMax
- Public official docs expose both OpenAI-compatible and Anthropic-compatible APIs
- Public docs also describe Claude Code compatibility
- Practical adapter choice: both OpenAI-style tool rendering and Anthropic-style tool rendering

## Kimi / Moonshot
- Public official materials emphasize OpenAI-compatible API usage and tool-calling / MCP in Playground
- Public indexed materials do not expose a stable standalone native skills package spec
- Practical adapter choice: OpenAI-compatible `tools=[...]` rendering
