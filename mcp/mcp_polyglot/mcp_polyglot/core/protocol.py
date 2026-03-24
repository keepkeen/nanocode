from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


JSON = Dict[str, Any]


@dataclass(slots=True)
class JsonRpcRequest:
    jsonrpc: str
    method: str
    id: Optional[Any] = None
    params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: JSON) -> "JsonRpcRequest":
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            method=data["method"],
            id=data.get("id"),
            params=data.get("params", {}),
        )


@dataclass(slots=True)
class JsonRpcResponse:
    jsonrpc: str = "2.0"
    id: Optional[Any] = None
    result: Optional[JSON] = None
    error: Optional[JSON] = None

    def to_dict(self) -> JSON:
        payload: JSON = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            payload["error"] = self.error
        else:
            payload["result"] = self.result or {}
        return payload


def make_error(code: int, message: str, data: Any = None) -> JSON:
    payload: JSON = {"code": code, "message": message}
    if data is not None:
        payload["data"] = data
    return payload
