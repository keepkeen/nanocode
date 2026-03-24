from multi_vendor_skills.examples.weather_skill import WEATHER_SKILL
from multi_vendor_skills.runtimes import OpenAICompatibleRuntime

runtime = OpenAICompatibleRuntime(
    provider="minimax",
    base_url="https://api.minimax.io/v1",
    api_key="YOUR_API_KEY",
    model="MiniMax-M2.5",
)

response = runtime.invoke(
    WEATHER_SKILL,
    "Please summarize Hangzhou weather for 3 days and give packing advice.",
)
print(response)
