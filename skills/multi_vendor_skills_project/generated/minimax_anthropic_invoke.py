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
