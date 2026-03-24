from multi_vendor_skills.examples.weather_skill import WEATHER_SKILL
from multi_vendor_skills.runtimes import OpenAICompatibleRuntime

runtime = OpenAICompatibleRuntime(
    provider="glm",
    base_url="https://open.bigmodel.cn/api/paas/v4",
    api_key="YOUR_API_KEY",
    model="glm-5",
)

response = runtime.invoke(
    WEATHER_SKILL,
    "Please summarize Hangzhou weather for 3 days and give packing advice.",
)
print(response)
