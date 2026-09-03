"""API Proxy Module Configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

__all__ = ["ApiproxyConfig"]


@dataclass
class ApiproxyConfig:
    """Конфигурация apiproxy-модуля.

    whitelist — мёртвое поле (совместимость тестов), не источник collect.
    MIA_APIPROXY_WHITELIST игнорируется.
    """

    whitelist: list[str] = field(default_factory=list)
    method_timeout: float = 30.0

    @classmethod
    def from_env(cls) -> ApiproxyConfig:
        timeout_raw = os.getenv("MIA_APIPROXY_METHOD_TIMEOUT", "")
        method_timeout = float(timeout_raw) if timeout_raw else 30.0
        return cls(method_timeout=method_timeout)
