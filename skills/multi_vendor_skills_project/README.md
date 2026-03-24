# Multi-Vendor Skills

This project implements a unified `SkillDefinition` abstraction and renders the same skill into multiple official or officially-compatible formats across:

- OpenAI / ChatGPT Skills (Agent Skills package)
- Claude / Claude Code Skills (Agent Skills package)
- Claude Code Subagents (official adjacent reusable format)
- DeepSeek Function Calling
- Zhipu GLM Function Calling
- MiniMax OpenAI-compatible tools
- MiniMax Anthropic-compatible tools
- Kimi / Moonshot OpenAI-compatible tools

## Why the code is split this way

There is no single cross-vendor native "skills" format.

- OpenAI ChatGPT/Codex and Anthropic Skills use the `SKILL.md` family.
- Claude Code also supports subagents as a first-class reusable prompt + tool policy format.
- DeepSeek, GLM, MiniMax, and Kimi publicly expose more stable tool/function-calling interfaces than a native file-based skills package.

So this project separates:

1. **Skill definition**: a provider-neutral Python dataclass
2. **Package renderers**: render to `SKILL.md`-style artifacts
3. **Tool schema renderers**: render to provider API tool definitions
4. **Invocation runtimes**: execute OpenAI-compatible or Anthropic-compatible tool loops

## Project layout

```text
multi_vendor_skills/
├── models.py
├── yaml_utils.py
├── cli.py
├── examples/
│   └── weather_skill.py
├── renderers/
│   ├── agent_skills.py
│   ├── claude_subagent.py
│   ├── openai_tools.py
│   └── anthropic_tools.py
└── runtimes/
    ├── openai_runtime.py
    └── anthropic_runtime.py
```

## Sample concrete skill

The included sample skill is `travel-weather-briefing`.

It contains:

- a reusable instruction set
- a JSON-schema tool definition
- a local Python executor (`get_mock_weather`) so the adapter design is complete

## Generate all outputs

```bash
python -m multi_vendor_skills.cli --out generated
```

## Example rendered outputs

- `generated/chatgpt/.../SKILL.md`
- `generated/claude-code/.../SKILL.md`
- `generated/claude-code/travel-weather-briefing.md` (subagent)
- `generated/deepseek/tools.json`
- `generated/glm/tools.json`
- `generated/minimax/openai-tools.json`
- `generated/minimax/anthropic-tools.json`
- `generated/kimi/tools.json`

## Example runtime usage

### DeepSeek / GLM / MiniMax / Kimi

```python
from multi_vendor_skills.examples.weather_skill import WEATHER_SKILL
from multi_vendor_skills.runtimes import OpenAICompatibleRuntime

runtime = OpenAICompatibleRuntime(
    provider="deepseek",
    base_url="https://api.deepseek.com",
    api_key="YOUR_API_KEY",
    model="deepseek-chat",
)

response = runtime.invoke(
    WEATHER_SKILL,
    "Please summarize Hangzhou weather for 3 days and give packing advice.",
)
print(response)
```

### MiniMax Anthropic-compatible endpoint

```python
from multi_vendor_skills.examples.weather_skill import WEATHER_SKILL
from multi_vendor_skills.runtimes import AnthropicCompatibleRuntime

runtime = AnthropicCompatibleRuntime(
    base_url="https://api.minimax.io/anthropic",
    api_key="YOUR_API_KEY",
    model="MiniMax-M2.5",
)

response = runtime.invoke(
    WEATHER_SKILL,
    "Please summarize Beijing weather for 2 days and give packing advice.",
)
print(response)
```

## Notes

- The generated ChatGPT and Claude skill packages are standards-first `SKILL.md` packages.
- The Claude Code subagent output is included because Anthropic documents it explicitly and it is useful in practice.
- The Kimi adapter is rendered through the OpenAI-compatible tool schema path.
- The mock weather tool is intentionally local and dependency-free so the architecture stays easy to study.
