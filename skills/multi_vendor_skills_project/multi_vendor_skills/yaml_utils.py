from __future__ import annotations

from typing import Any


def _quote(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def dump_yaml(data: dict[str, Any], indent: int = 0) -> str:
    lines: list[str] = []
    for key, value in data.items():
        prefix = " " * indent + f"{key}:"
        if isinstance(value, dict):
            if not value:
                lines.append(prefix + " {}")
            else:
                lines.append(prefix)
                lines.append(dump_yaml(value, indent + 2))
        elif isinstance(value, list):
            if not value:
                lines.append(prefix + " []")
            else:
                lines.append(prefix)
                for item in value:
                    if isinstance(item, dict):
                        lines.append(" " * (indent + 2) + "-")
                        lines.append(dump_yaml(item, indent + 4))
                    else:
                        lines.append(" " * (indent + 2) + f"- {_scalar(item)}")
        else:
            lines.append(prefix + f" {_scalar(value)}")
    return "\n".join(lines)


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return _quote(str(value))
