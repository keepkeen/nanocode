from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

import requests


class Transport(ABC):
    @abstractmethod
    def post(self, url: str, headers: Dict[str, str], json_body: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class RequestsTransport(Transport):
    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout

    def post(self, url: str, headers: Dict[str, str], json_body: Dict[str, Any]) -> Dict[str, Any]:
        response = requests.post(url, headers=headers, json=json_body, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"HTTP {response.status_code} calling {url}: {response.text}"
            ) from exc
        return response.json()
