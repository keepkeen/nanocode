from __future__ import annotations

import json

from .weather_tool import WeatherMcpServer


def pretty(title: str, data: dict) -> None:
    print("=" * 80)
    print(title)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print()


def main() -> None:
    server = WeatherMcpServer()

    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"roots": {"listChanged": False}},
            "clientInfo": {"name": "demo-client", "version": "0.1.0"},
        },
    }
    pretty("initialize =>", server.handle_dict(initialize))

    initialized = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    pretty("notifications/initialized =>", server.handle_dict(initialized))

    list_tools = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    pretty("tools/list =>", server.handle_dict(list_tools))

    call_tool = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "weather.get_current_weather",
            "arguments": {"city": "Hangzhou", "unit": "celsius"},
        },
    }
    pretty("tools/call =>", server.handle_dict(call_tool))


if __name__ == "__main__":
    main()
