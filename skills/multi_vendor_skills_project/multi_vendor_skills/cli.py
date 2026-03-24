from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from multi_vendor_skills.examples.weather_skill import WEATHER_SKILL
from multi_vendor_skills.models import RenderedArtifact
from multi_vendor_skills.renderers import (
    AgentSkillsRenderer,
    AnthropicToolsRenderer,
    ChatGPTSkillsRenderer,
    ClaudeSubagentRenderer,
    DeepSeekToolsRenderer,
    OpenAICompatibleToolsRenderer,
)


def _write_all(artifacts: list[RenderedArtifact], out_dir: Path) -> None:
    for artifact in artifacts:
        artifact.write_into(out_dir)


def generate(out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    skill = WEATHER_SKILL

    render_plan = [
        ("chatgpt_skill", ChatGPTSkillsRenderer(root_prefix="chatgpt")),
        ("claude_skill", AgentSkillsRenderer(root_prefix="claude-code")),
        (
            "claude_subagent",
            ClaudeSubagentRenderer(tools=["Read", "Write", "Bash", "WebFetch"], root_prefix="claude-code"),
        ),
        ("deepseek_tools", DeepSeekToolsRenderer(output_path="deepseek/tools.json")),
        ("glm_tools", OpenAICompatibleToolsRenderer(output_path="glm/tools.json")),
        ("minimax_openai_tools", OpenAICompatibleToolsRenderer(output_path="minimax/openai-tools.json")),
        ("minimax_anthropic_tools", AnthropicToolsRenderer(output_path="minimax/anthropic-tools.json")),
        ("kimi_tools", OpenAICompatibleToolsRenderer(output_path="kimi/tools.json")),
    ]

    manifest: dict[str, list[str]] = {}
    for label, renderer in render_plan:
        artifacts = renderer.render(skill)
        _write_all(artifacts, out_dir)
        manifest[label] = [artifact.path for artifact in artifacts]

    docs = {
        "chatgpt_usage.txt": (
            "1. Zip the chatgpt/travel-weather-briefing directory.\n"
            "2. In ChatGPT Skills, upload/install the package.\n"
            "3. Example prompt: Use the travel-weather-briefing skill to summarize Hangzhou weather for 3 days.\n"
        ),
        "claude_code_usage.txt": (
            "Option A: install the rendered skill package via Claude skills/plugin workflow.\n"
            "Option B: use the rendered subagent file under .claude/agents/.\n"
            "Example prompt: Use the travel-weather-briefing skill for Beijing for 2 days.\n"
        ),
        "deepseek_invoke.py": _openai_invoke_script(
            provider_name="deepseek",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        ),
        "glm_invoke.py": _openai_invoke_script(
            provider_name="glm",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            model="glm-5",
        ),
        "minimax_openai_invoke.py": _openai_invoke_script(
            provider_name="minimax",
            base_url="https://api.minimax.io/v1",
            model="MiniMax-M2.5",
        ),
        "kimi_invoke.py": _openai_invoke_script(
            provider_name="kimi",
            base_url="https://api.moonshot.cn/v1",
            model="kimi-k2-0905-preview",
        ),
        "minimax_anthropic_invoke.py": _anthropic_invoke_script(),
        "manifest.json": json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    }
    for rel_path, content in docs.items():
        (out_dir / rel_path).write_text(content, encoding="utf-8")


def _openai_invoke_script(provider_name: str, base_url: str, model: str) -> str:
    return f'''from multi_vendor_skills.examples.weather_skill import WEATHER_SKILL
from multi_vendor_skills.runtimes import OpenAICompatibleRuntime

runtime = OpenAICompatibleRuntime(
    provider="{provider_name}",
    base_url="{base_url}",
    api_key="YOUR_API_KEY",
    model="{model}",
)

response = runtime.invoke(
    WEATHER_SKILL,
    "Please summarize Hangzhou weather for 3 days and give packing advice.",
)
print(response)
'''



def _anthropic_invoke_script() -> str:
    return '''from multi_vendor_skills.examples.weather_skill import WEATHER_SKILL
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
'''



def main() -> None:
    parser = argparse.ArgumentParser(description="Generate multi-vendor skill artifacts.")
    parser.add_argument(
        "--out",
        default="generated",
        help="Output directory for rendered artifacts (default: ./generated)",
    )
    args = parser.parse_args()
    generate(Path(args.out))


if __name__ == "__main__":
    main()
