from __future__ import annotations

from ..core.server import BaseMcpServer
from ..core.tool import BaseMcpTool, TextContent, ToolAnnotations, ToolCallResult


class WeatherTool(BaseMcpTool):
    def __init__(self) -> None:
        super().__init__(
            name="weather.get_current_weather",
            title="Get current weather",
            description=(
                "Get the current weather of a city. "
                "Use this tool when the user asks for weather, temperature, or conditions."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name, for example: Beijing, Shanghai, San Francisco",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature unit",
                        "default": "celsius",
                    },
                },
                "required": ["city"],
            },
            annotations=ToolAnnotations(
                title="Weather",
                read_only_hint=True,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=True,
            ),
        )

    def call(self, arguments: dict) -> ToolCallResult:
        city = str(arguments.get("city", "")).strip()
        unit = str(arguments.get("unit", "celsius")).strip() or "celsius"

        if not city:
            return ToolCallResult(
                content=[TextContent("Missing required field: city")],
                is_error=True,
                structured_content={"error": "Missing required field: city"},
            )

        fake_temperature_c = {
            "beijing": 22,
            "shanghai": 25,
            "san francisco": 18,
            "hangzhou": 24,
            "shenzhen": 28,
        }.get(city.lower(), 21)

        if unit == "fahrenheit":
            temp = round(fake_temperature_c * 9 / 5 + 32, 1)
            unit_label = "°F"
        else:
            temp = fake_temperature_c
            unit_label = "°C"

        structured = {
            "city": city,
            "unit": unit,
            "temperature": temp,
            "condition": "sunny",
        }

        return ToolCallResult(
            content=[
                TextContent(
                    f"The current weather in {city} is sunny, {temp}{unit_label}."
                )
            ],
            is_error=False,
            structured_content=structured,
        )


class WeatherMcpServer(BaseMcpServer):
    def __init__(self) -> None:
        super().__init__(
            name="weather-mcp-server",
            version="0.1.0",
            protocol_version="2025-06-18",
            instructions="This server exposes a single weather tool.",
        )
        self.register_tool(WeatherTool())
