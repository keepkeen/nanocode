from multi_vendor_skills.examples.weather_skill import WEATHER_SKILL
from multi_vendor_skills.runtimes import OpenAICompatibleRuntime

runtime = OpenAICompatibleRuntime(
    provider="kimi",
    base_url="https://api.moonshot.cn/v1",
    api_key="YOUR_API_KEY",
    model="kimi-k2-0905-preview",
)

response = runtime.invoke(
    WEATHER_SKILL,
    "Please summarize Hangzhou weather for 3 days and give packing advice.",
)
print(response)
