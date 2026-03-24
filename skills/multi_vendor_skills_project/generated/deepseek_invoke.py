from multi_vendor_skills.examples.weather_skill import WEATHER_SKILL
from multi_vendor_skills.runtimes import OpenAICompatibleRuntime

runtime = OpenAICompatibleRuntime(
    provider="deepseek",
    base_url="https://api.deepseek.com",
    api_key="YOUR_API_KEY",
    model="deepseek-chat",
)

response = runtime.invoke(
    WEATHER_SKILL,
    "Please summarize Hangzhou weather for 3 days and give packing advice.",
)
print(response)
