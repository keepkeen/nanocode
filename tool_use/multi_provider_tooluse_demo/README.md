# Multi-provider Tool Use Demo

This package shows a fully decoupled tool-use implementation across six providers / protocol families:

- OpenAI Responses API (`/v1/responses`)
- DeepSeek (OpenAI-compatible chat completions)
- GLM / Zhipu (chat completions)
- MiniMax (OpenAI-compatible path)
- Kimi / Moonshot (OpenAI-compatible path, but `role=tool` reply includes `name`)
- Claude / Anthropic Messages API (`tool_use` / `tool_result` blocks)

## Layout

- `models.py`: normalized entities
- `tools.py`: abstract tool base class, tool registry, demo weather tool
- `agent.py`: provider-independent tool execution loop
- `transports.py`: HTTP transport abstraction
- `adapters/`: provider/protocol-specific serializers and parsers
- `providers.py`: convenience factories
- `examples/demo.py`: live demo entrypoint
- `tests/self_test.py`: protocol-shape self-checks

## Quick start

```bash
python -m pip install -r /mnt/data/multi_provider_tooluse_demo/requirements.txt
PYTHONPATH=/mnt/data python /mnt/data/multi_provider_tooluse_demo/tests/self_test.py
```

## Live calls

Set one or more provider API keys:

- `OPENAI_API_KEY`
- `DEEPSEEK_API_KEY`
- `ZAI_API_KEY`
- `MINIMAX_API_KEY`
- `MOONSHOT_API_KEY`
- `ANTHROPIC_API_KEY`

Then run:

```bash
PYTHONPATH=/mnt/data python /mnt/data/multi_provider_tooluse_demo/examples/demo.py
```

## Important note on Claude Code

Anthropic now positions the old Claude Code SDK as the Claude Agent SDK.
For **custom tool calling protocol** interoperability, the correct low-level target is still the Anthropic **Messages API tool-use format** (`tools`, `tool_use`, `tool_result`).
This repo therefore implements Claude custom tools via the Messages API adapter, which is the right abstraction level to compare with the other vendors.
