from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable
import shutil

from multi_vendor_skills.examples.weather_skill import WEATHER_SKILL
from multi_vendor_skills.models import SkillDefinition, ToolSpec
from multi_vendor_skills.renderers import (
    AgentSkillsRenderer,
    AnthropicToolsRenderer,
    ChatGPTSkillsRenderer,
    ClaudeSubagentRenderer,
    DeepSeekToolsRenderer,
    OpenAICompatibleToolsRenderer,
)

from .models import LoadedSkill, SkillsOptions
from .tool_runtime import RuntimeTool


BUILTIN_IMPORTS = {
    "travel-weather-briefing": "from multi_vendor_skills.examples.weather_skill import WEATHER_SKILL as SKILL\n",
}


def builtin_skill_definitions() -> dict[str, SkillDefinition]:
    return {
        WEATHER_SKILL.name: WEATHER_SKILL,
    }


def available_render_targets() -> list[str]:
    return [
        "chatgpt",
        "claude-code",
        "claude-subagent",
        "deepseek",
        "glm",
        "kimi",
        "minimax-openai",
        "minimax-anthropic",
    ]


@dataclass(slots=True)
class SkillManager:
    project_root: Path
    options: SkillsOptions

    def discover(self) -> dict[str, LoadedSkill]:
        discovered = {name: _loaded_from_definition(skill, origin="builtin") for name, skill in builtin_skill_definitions().items()}
        for root in self._search_roots():
            for skill_root in self._iter_skill_roots(root):
                canonical = self._load_python_skills(skill_root)
                if canonical:
                    for loaded in canonical:
                        discovered[loaded.name] = loaded
                    continue
                if (skill_root / "SKILL.md").exists():
                    loaded = _load_markdown_skill(skill_root)
                    discovered.setdefault(loaded.name, loaded)
        return discovered

    def load_selected(self, selected_names: Iterable[str] | None = None) -> list[LoadedSkill]:
        catalog = self.discover()
        selected = list(dict.fromkeys(selected_names or self.options.enabled))
        if not selected:
            return []
        loaded: list[LoadedSkill] = []
        for name in selected:
            if name not in catalog:
                raise KeyError(f"Unknown skill: {name}")
            loaded.append(catalog[name])
        return loaded

    def build_runtime_tools(self, skills: Iterable[LoadedSkill]) -> list[RuntimeTool]:
        tools: list[RuntimeTool] = []
        for skill in skills:
            if skill.instruction_only:
                continue
            definition = _canonical_definition(skill)
            for tool in definition.tools:
                tools.append(_runtime_tool_from_skill(skill.name, tool))
        return tools

    def render(
        self,
        *,
        names: Iterable[str] | None = None,
        targets: Iterable[str] | None = None,
        out_dir: Path | None = None,
    ) -> list[Path]:
        catalog = self.discover()
        selected_names = list(dict.fromkeys(names or catalog.keys()))
        selected_targets = list(dict.fromkeys(targets or self.options.auto_render_targets))
        output_dir = out_dir or (self.project_root / ".nanocli" / "generated")
        output_dir.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        for name in selected_names:
            if name not in catalog:
                raise KeyError(f"Unknown skill: {name}")
            definition = _canonical_definition(catalog[name])
            for target in selected_targets:
                renderer = _renderer_for_target(target, definition.name)
                for artifact in renderer.render(definition):
                    written.append(artifact.write_into(output_dir))
        return written

    def install(self, source: str, destination_root: Path | None = None) -> Path:
        destination_root = destination_root or (self.project_root / ".nanocli" / "skills")
        destination_root.mkdir(parents=True, exist_ok=True)
        builtins = builtin_skill_definitions()
        if source in builtins:
            target_root = destination_root / source
            if target_root.exists():
                shutil.rmtree(target_root)
            target_root.mkdir(parents=True, exist_ok=True)
            import_stub = BUILTIN_IMPORTS.get(source)
            if import_stub:
                (target_root / self.options.runtime_entrypoint).write_text(import_stub, encoding="utf-8")
            renderer = AgentSkillsRenderer(root_prefix="")
            for artifact in renderer.render(builtins[source]):
                artifact.write_into(target_root)
            nested_root = target_root / source
            if nested_root.exists() and nested_root.is_dir():
                for path in nested_root.iterdir():
                    shutil.move(str(path), target_root / path.name)
                nested_root.rmdir()
            return target_root

        source_path = Path(source).expanduser().resolve()
        skill_root = source_path if source_path.is_dir() else source_path.parent
        has_python = (skill_root / self.options.runtime_entrypoint).exists()
        has_markdown = (skill_root / "SKILL.md").exists()
        if not has_python and not has_markdown:
            raise FileNotFoundError(f"{source} is not a skill package root")
        target_root = destination_root / skill_root.name
        if target_root.exists():
            shutil.rmtree(target_root)
        shutil.copytree(skill_root, target_root)
        return target_root

    def _search_roots(self) -> list[Path]:
        roots: list[Path] = []
        for raw in self.options.project_paths:
            roots.append((self.project_root / raw).resolve())
        for raw in self.options.user_paths:
            roots.append(Path(raw).expanduser().resolve())
        return roots

    def _iter_skill_roots(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        candidates: list[Path] = []
        if self._is_skill_root(root):
            candidates.append(root)
        for path in sorted(root.iterdir()):
            if path.is_dir() and self._is_skill_root(path):
                candidates.append(path)
        return candidates

    def _is_skill_root(self, root: Path) -> bool:
        return (root / self.options.runtime_entrypoint).exists() or (root / "SKILL.md").exists()

    def _load_python_skills(self, root: Path) -> list[LoadedSkill]:
        entrypoint = root / self.options.runtime_entrypoint
        if not entrypoint.exists():
            return []
        module = _load_module(entrypoint)
        loaded: list[LoadedSkill] = []
        for definition in _extract_definitions(module):
            loaded.append(_loaded_from_definition(definition, origin="python", root_dir=root, entrypoint=str(entrypoint.name)))
        return loaded


def _loaded_from_definition(
    skill: SkillDefinition,
    *,
    origin: str,
    root_dir: Path | None = None,
    entrypoint: str | None = None,
) -> LoadedSkill:
    return LoadedSkill(
        name=skill.name,
        title=skill.title,
        description=skill.description,
        root_dir=root_dir or (Path("<builtin>") / skill.name),
        instructions=skill.instructions.strip(),
        references=dict(skill.references),
        scripts=dict(skill.scripts),
        metadata={
            **{str(key): str(value) for key, value in skill.metadata.items()},
            "origin": origin,
            "compatibility": skill.compatibility or "",
            "license": skill.license or "",
            "canonical_definition": skill,
        },
        tools=[
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "strict": tool.strict,
            }
            for tool in skill.tools
        ],
        instruction_only=False,
        entrypoint=entrypoint,
    )


def _canonical_definition(skill: LoadedSkill) -> SkillDefinition:
    definition = skill.metadata.get("canonical_definition")
    if isinstance(definition, SkillDefinition):
        return definition
    return SkillDefinition(
        name=skill.name,
        title=skill.title,
        description=skill.description,
        instructions=skill.instructions,
        references=skill.references,
        scripts=skill.scripts,
        metadata={str(key): str(value) for key, value in skill.metadata.items() if key != "canonical_definition"},
    )


def _renderer_for_target(target: str, skill_name: str):
    if target == "chatgpt":
        return ChatGPTSkillsRenderer(root_prefix="chatgpt")
    if target == "claude-code":
        return AgentSkillsRenderer(root_prefix="claude-code")
    if target == "claude-subagent":
        return ClaudeSubagentRenderer(
            tools=["Read", "Write", "Bash", "WebFetch"],
            root_prefix="claude-code",
        )
    if target == "deepseek":
        return DeepSeekToolsRenderer(output_path=f"deepseek/{skill_name}/tools.json")
    if target == "glm":
        return OpenAICompatibleToolsRenderer(output_path=f"glm/{skill_name}/tools.json")
    if target == "kimi":
        return OpenAICompatibleToolsRenderer(output_path=f"kimi/{skill_name}/tools.json")
    if target == "minimax-openai":
        return OpenAICompatibleToolsRenderer(output_path=f"minimax-openai/{skill_name}/tools.json")
    if target == "minimax-anthropic":
        return AnthropicToolsRenderer(output_path=f"minimax-anthropic/{skill_name}/tools.json")
    raise KeyError(f"Unknown render target: {target}")


def _load_markdown_skill(root: Path) -> LoadedSkill:
    skill_path = root / "SKILL.md"
    text = skill_path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    title, instructions = _extract_title_and_instructions(body, default_title=frontmatter.get("name", root.name))
    references = _load_text_tree(root / "references")
    scripts = _load_text_tree(root / "scripts")
    return LoadedSkill(
        name=str(frontmatter.get("name") or root.name),
        title=title,
        description=str(frontmatter.get("description") or title),
        root_dir=root,
        instructions=instructions,
        references=references,
        scripts=scripts,
        metadata={**frontmatter, "origin": "instruction-only"},
        instruction_only=True,
    )


def _load_module(entrypoint: Path) -> ModuleType:
    module_name = f"nanocli_skill_{sha1(str(entrypoint).encode('utf-8')).hexdigest()[:12]}"
    spec = spec_from_file_location(module_name, entrypoint)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load skill module from {entrypoint}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _extract_definitions(module: ModuleType) -> list[SkillDefinition]:
    single = getattr(module, "SKILL", None)
    many = getattr(module, "SKILLS", None)
    definitions: list[SkillDefinition] = []
    if isinstance(single, SkillDefinition):
        definitions.append(single)
    if isinstance(many, list):
        definitions.extend(item for item in many if isinstance(item, SkillDefinition))
    if not definitions:
        raise RuntimeError("skill.py must export SKILL or SKILLS with SkillDefinition values")
    for definition in definitions:
        definition.validate()
    return definitions


def _runtime_tool_from_skill(skill_name: str, tool_spec: ToolSpec) -> RuntimeTool:
    def handler(arguments: dict[str, Any], *_args: Any) -> Any:
        if tool_spec.executor is None:
            raise RuntimeError(f"Skill tool {tool_spec.name} has no local executor.")
        return tool_spec.executor(arguments)

    return RuntimeTool(
        name=tool_spec.name,
        description=f"[skill:{skill_name}] {tool_spec.description}",
        parameters=tool_spec.parameters,
        strict=tool_spec.strict,
        handler=handler,
        metadata={"skill_name": skill_name, "tool_name": tool_spec.name},
    )


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text
    frontmatter_lines = parts[0].splitlines()[1:]
    frontmatter = _parse_simple_yaml(frontmatter_lines)
    return frontmatter, parts[1]


def _parse_simple_yaml(lines: Iterable[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip().strip("'\"")
    return parsed


def _extract_title_and_instructions(text: str, *, default_title: str) -> tuple[str, str]:
    stripped = text.strip()
    if stripped.startswith("# "):
        first_line, _, rest = stripped.partition("\n")
        return first_line[2:].strip(), rest.strip()
    return default_title, stripped


def _load_text_tree(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[str(path.relative_to(root))] = path.read_text(encoding="utf-8")
    return files
