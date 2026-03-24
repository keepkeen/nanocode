from __future__ import annotations

from typing import Optional
import json
import urllib.request

from ..base import BaseRuntime
from ..models import ProviderRequest


class OpenAIRuntime(BaseRuntime):
    def invoke(self, request: ProviderRequest, *, api_key: str, base_url: Optional[str] = None) -> object:
        target_base = (base_url or "https://api.openai.com/v1").rstrip("/")
        try:
            from openai import OpenAI  # type: ignore
            client = OpenAI(api_key=api_key, base_url=target_base)
            if request.endpoint_style == "responses":
                return client.responses.create(**request.payload)
            if request.endpoint_style == "chat.completions":
                return client.chat.completions.create(**request.payload)
        except Exception:
            pass
        return _http_post(target_base + request.path, request, api_key)


class OpenAICompatibleRuntime(BaseRuntime):
    def invoke(self, request: ProviderRequest, *, api_key: str, base_url: Optional[str] = None) -> object:
        if not base_url:
            raise ValueError("base_url is required for OpenAI-compatible providers")
        target_base = base_url.rstrip("/")
        try:
            from openai import OpenAI  # type: ignore
            client = OpenAI(api_key=api_key, base_url=target_base)
            if request.endpoint_style == "chat.completions":
                return client.chat.completions.create(**request.payload)
        except Exception:
            pass
        return _http_post(target_base + request.path, request, api_key)


class AnthropicRuntime(BaseRuntime):
    def invoke(self, request: ProviderRequest, *, api_key: str, base_url: Optional[str] = None) -> object:
        target_base = (base_url or "https://api.anthropic.com").rstrip("/")
        try:
            from anthropic import Anthropic  # type: ignore
            client = Anthropic(api_key=api_key)
            if request.endpoint_style == "messages":
                payload = dict(request.payload)
                betas = []
                beta_header = request.headers.get("anthropic-beta")
                if beta_header:
                    betas = [item.strip() for item in beta_header.split(",") if item.strip()]
                return client.beta.messages.create(betas=betas, **payload) if betas else client.messages.create(**payload)
        except Exception:
            pass
        return _http_post(target_base + request.path, request, api_key, anthropic=True)


def _http_post(url: str, request: ProviderRequest, api_key: str, anthropic: bool = False) -> object:
    headers = {"Content-Type": "application/json", **request.headers}
    if anthropic:
        headers.update({"x-api-key": api_key, "anthropic-version": "2023-06-01"})
    else:
        headers.update({"Authorization": f"Bearer {api_key}"})
    body = json.dumps(request.payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))
