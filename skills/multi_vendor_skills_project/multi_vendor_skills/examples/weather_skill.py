from __future__ import annotations

from multi_vendor_skills.models import InvocationExample, SkillDefinition, ToolSpec


_MOCK_WEATHER_DB = {
    "hangzhou": {
        "location": "Hangzhou, Zhejiang",
        "forecast": [
            {"day": 1, "condition": "Cloudy", "high_c": 25, "low_c": 18, "rain_probability": 0.2},
            {"day": 2, "condition": "Rain", "high_c": 22, "low_c": 17, "rain_probability": 0.8},
            {"day": 3, "condition": "Sunny", "high_c": 27, "low_c": 19, "rain_probability": 0.1},
        ],
    },
    "beijing": {
        "location": "Beijing",
        "forecast": [
            {"day": 1, "condition": "Sunny", "high_c": 21, "low_c": 11, "rain_probability": 0.0},
            {"day": 2, "condition": "Windy", "high_c": 18, "low_c": 9, "rain_probability": 0.0},
            {"day": 3, "condition": "Cloudy", "high_c": 19, "low_c": 10, "rain_probability": 0.1},
        ],
    },
}


def get_mock_weather(arguments: dict) -> dict:
    location = str(arguments.get("location", "")).strip().lower()
    days = int(arguments.get("days", 3))
    if location not in _MOCK_WEATHER_DB:
        return {
            "error": f"Unknown location {location!r}. Available fixtures: {sorted(_MOCK_WEATHER_DB)}"
        }
    forecast = _MOCK_WEATHER_DB[location]
    return {
        "location": forecast["location"],
        "forecast": forecast["forecast"][: max(1, min(days, 7))],
        "unit": "celsius",
        "source": "local_fixture",
    }


WEATHER_SKILL = SkillDefinition(
    name="travel-weather-briefing",
    title="Travel Weather Briefing",
    description=(
        "Create concise weather briefings for travel planning. Use when the user asks for a weather summary, "
        "packing advice, or short itinerary weather guidance for a city or trip. If forecast data is needed, call "
        "the weather tool instead of guessing."
    ),
    instructions="""
Act as a weather-trip briefing specialist.

Workflow:
1. If the city is missing, ask for it.
2. If a forecast tool is available, use it to fetch the weather instead of inventing conditions.
3. Summarize the next few days in plain language.
4. Give practical packing advice, mentioning rain gear if rain probability is high.
5. Keep the answer compact and decision-oriented.
""",
    tools=[
        ToolSpec(
            name="get_mock_weather",
            description="Look up a short weather forecast for a city fixture.",
            strict=True,
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City key, e.g. hangzhou or beijing",
                    },
                    "days": {
                        "type": "integer",
                        "description": "How many forecast days to retrieve",
                        "minimum": 1,
                        "maximum": 7,
                    },
                },
                "required": ["location", "days"],
                "additionalProperties": False,
            },
            executor=get_mock_weather,
        )
    ],
    examples=[
        InvocationExample(
            title="Weather + packing",
            prompt="给我做一个杭州未来3天的天气和穿衣建议",
        ),
        InvocationExample(
            title="Travel summary",
            prompt="Summarize the weather in Beijing for the next 2 days for my trip",
        ),
    ],
    references={
        "TOOLING.md": "This sample skill uses a local fixture tool so the end-to-end tool loop can be demonstrated without external APIs.\n"
    },
    scripts={
        "get_mock_weather.py": "from multi_vendor_skills.examples.weather_skill import get_mock_weather\n"
    },
    compatibility="Designed to be rendered either as Agent Skills or as provider-specific tool schemas.",
    metadata={
        "author": "chatgpt",
        "sample": "true",
        "version": "0.1.0",
    },
)
