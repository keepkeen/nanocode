---
name: "travel-weather-briefing"
description: "Create concise weather briefings for travel planning. Use when the user asks for a weather summary, packing advice, or short itinerary weather guidance for a city or trip. If forecast data is needed, call the weather tool instead of guessing."
compatibility: "Designed to be rendered either as Agent Skills or as provider-specific tool schemas."
metadata:
  author: "chatgpt"
  sample: "true"
  version: "0.1.0"
---

# Travel Weather Briefing

Act as a weather-trip briefing specialist.

Workflow:
1. If the city is missing, ask for it.
2. If a forecast tool is available, use it to fetch the weather instead of inventing conditions.
3. Summarize the next few days in plain language.
4. Give practical packing advice, mentioning rain gear if rain probability is high.
5. Keep the answer compact and decision-oriented.

## Examples

- Weather + packing: `给我做一个杭州未来3天的天气和穿衣建议`

- Travel summary: `Summarize the weather in Beijing for the next 2 days for my trip`
