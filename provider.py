"""ApiProxyProvider — основной провайдер apiproxy-модуля.

Предоставляет:
- call(module_name, method_name, kwargs, token) — вызов метода
- list_api(module_name) — список методов для CLI/OpenAPI
"""
from __future__ import annotations

from typing import Any



from .config import ApiproxyConfig
from .registry import MethodRegistry
from .middleware import AuthMiddleware
from .converter import call_method


__all__ = ["ApiProxyProvider"]


class ApiProxyProvider:
    """Провайдер API Proxy.

    Основной интерфейс для вызова методов модулей.
    """

    def __init__(
        self,
        config: ApiproxyConfig | None = None,
        auth_provider: Any | None = None,
        log: Any | None = None,
    ) -> None:
        self._config = config or ApiproxyConfig()
        self._registry = MethodRegistry(log=log)
        self._middleware = AuthMiddleware(auth_provider=auth_provider, log=log)
        self._auth_provider = auth_provider
        self._llm_provider: Any | None = None
        self._term_provider: Any | None = None
        self._state: Any | None = None
        self._log = log

    @property
    def registry(self) -> MethodRegistry:
        """Доступ к реестру методов."""
        return self._registry

    @property
    def middleware(self) -> AuthMiddleware:
        """Доступ к middleware авторизации."""
        return self._middleware

    @property
    def auth_provider(self) -> Any | None:
        return self._auth_provider

    @property
    def llm_provider(self) -> Any | None:
        if self._llm_provider is not None:
            return self._llm_provider
        if self._state is None:
            return None
        try:
            from modules.llm.provider import LLMProvider
            self._llm_provider = self._state.services.resolve(LLMProvider)
        except Exception:
            return None
        return self._llm_provider

    @property
    def term_provider(self) -> Any | None:
        if self._term_provider is not None:
            return self._term_provider
        if self._state is None:
            return None
        try:
            from modules.term.provider import TermProvider
            self._term_provider = self._state.services.resolve(TermProvider)
        except Exception:
            return None
        return self._term_provider

    def bind_state(self, state: Any) -> None:
        self._state = state

    async def call(
        self,
        module_name: str,
        method_name: str,
        kwargs: dict[str, Any],
        token: str | None = None,
    ) -> dict[str, Any]:
        """Вызвать API-метод модуля.

        Источник истины — MethodRegistry (collect с `_provider` + `@task api=True`).
        Whitelist-константа не отвергает вызов.
        """
        return await call_method(
            registry=self._registry,
            middleware=self._middleware,
            module_name=module_name,
            method_name=method_name,
            kwargs=kwargs,
            token=token,
            log=self._log,
        )

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
