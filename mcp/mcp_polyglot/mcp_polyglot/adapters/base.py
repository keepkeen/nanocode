from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from ..core.server import BaseMcpServer
from ..core.tool import BaseMcpTool


JSON = Dict[str, object]


@dataclass(slots=True)
class NativeMcpEndpoint:
    server_label: str
    server_url: str
    server_description: Optional[str] = None
    authorization: Optional[str] = None
    connector_id: Optional[str] = None


class BaseProviderAdapter(ABC):
    provider_name: str = "base"
    supports_native_remote_mcp: bool = False
    supports_openai_compatible_function_calling: bool = False

    @abstractmethod
    def build_payload(
        self,
        *,
        prompt: str,
        model: str,
        server: Optional[BaseMcpServer] = None,
        tools: Optional[Iterable[BaseMcpTool]] = None,
        native_mcp: Optional[NativeMcpEndpoint] = None,
    ) -> JSON:
        raise NotImplementedError
