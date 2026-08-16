"""ApiProxyProvider — основной провайдер apiproxy-модуля.

Предоставляет:
- call(module_name, method_name, kwargs, token) — вызов метода
- list_api(module_name) — список методов для CLI/OpenAPI
- Whitelist модулей
"""
from __future__ import annotations

from typing import Any

from argenta_logging import get_logger

from core.task_decorator import task
from .config import ApiproxyConfig
from .registry import MethodRegistry, MethodMeta
from .middleware import AuthMiddleware
from .converter import call_method, ApiError

log = get_logger(__name__)

__all__ = ["ApiProxyProvider"]


class ApiProxyProvider:
    """Провайдер API Proxy.

    Основной интерфейс для вызова методов модулей.
    """

    def __init__(
        self,
        config: ApiproxyConfig | None = None,
        auth_provider: Any | None = None,
    ) -> None:
        self._config = config or ApiproxyConfig()
        self._registry = MethodRegistry()
        self._middleware = AuthMiddleware(auth_provider=auth_provider)
        self._auth_provider = auth_provider

    @property
    def registry(self) -> MethodRegistry:
        """Доступ к реестру методов."""
        return self._registry

    @property
    def middleware(self) -> AuthMiddleware:
        """Доступ к middleware авторизации."""
        return self._middleware

    @task(type="cpu", timeout=30.0)
    async def call(
        self,
        module_name: str,
        method_name: str,
        kwargs: dict[str, Any],
        token: str | None = None,
    ) -> dict[str, Any]:
        """Вызвать API-метод модуля.

        Полный цикл:
        1. Whitelist проверка
        2. Поиск метода
        3. Авторизация
        4. Валидация аргументов
        5. Вызов
        6. Нормализация ответа

        Args:
            module_name: Имя модуля (auth, workspace, llm).
            method_name: Имя метода.
            kwargs: Аргументы.
            token: Access token.

        Returns:
            {"data": result, "error": None} или {"data": None, "error": {...}}.
        """
        # Whitelist проверка
        if module_name not in self._config.whitelist:
            error = ApiError(403, f"Module '{module_name}' is not in whitelist")
            return error.to_dict()

        # Делегируем в converter
        return await call_method(
            registry=self._registry,
            middleware=self._middleware,
            module_name=module_name,
            method_name=method_name,
            kwargs=kwargs,
            token=token,
        )

    @task(type="cpu", timeout=5.0)
    def list_api(self, module_name: str | None = None) -> list[dict[str, Any]]:
        """Список доступных API-методов.

        Args:
            module_name: Фильтр по модулю (None = все).

        Returns:
            Список метаданных методов.
        """
        if module_name:
            methods = self._registry.list_methods(module_name)
        else:
            methods = self._registry.list_all_methods()

        return [
            {
                "module": m.module,
                "name": m.name,
                "description": m.description,
                "args": m.args,
                "return_type": m.return_type,
                "public": m.public,
                "required_permission": m.required_permission,
            }
            for m in methods
        ]
