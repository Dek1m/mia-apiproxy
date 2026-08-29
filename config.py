"""API Proxy Module Configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

__all__ = ["ApiproxyConfig"]

# Collect skip, если провайдера нет — admin не обязателен для старта apiproxy
_DEFAULT_WHITELIST: list[str] = ["auth", "workspace", "llm", "admin"]


@dataclass
class ApiproxyConfig:
    """Конфигурация apiproxy-модуля.

    Приоритет конфигурации:
    1. Прямые аргументы (наивысший)
    2. Переменные окружения (наименьший)
    """

    # Whitelist модулей (comma-separated в ENV)
    whitelist: list[str] = field(default_factory=lambda: list(_DEFAULT_WHITELIST))

    # Таймаут на выполнение метода (секунды)
    method_timeout: float = 30.0

    @classmethod
    def from_env(cls) -> ApiproxyConfig:
        """Создать конфигурацию из переменных окружения.

        Переменные:
            MIA_APIPROXY_WHITELIST: comma-separated список модулей
            MIA_APIPROXY_METHOD_TIMEOUT: таймаут метода
        """
        whitelist_raw = os.getenv("MIA_APIPROXY_WHITELIST", "")
        whitelist = (
            [m.strip() for m in whitelist_raw.split(",") if m.strip()]
            if whitelist_raw
            else list(_DEFAULT_WHITELIST)
        )

        timeout_raw = os.getenv("MIA_APIPROXY_METHOD_TIMEOUT", "")
        method_timeout = float(timeout_raw) if timeout_raw else 30.0

        return cls(whitelist=whitelist, method_timeout=method_timeout)
