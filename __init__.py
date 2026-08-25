"""API Proxy Module — прослойка между CLI и модулями Mia.

Собирает методы из модулей (auth, workspace, llm), выполняет авторизацию
через AuthMiddleware, конвертирует вызовы и возвращает нормализованные ответы.

Использование:
    app.load_module("apiproxy")

    proxy = app.services.resolve(ApiProxyProvider)
    result = await proxy.call("auth", "login", {"username": "admin", "password": "***"})
"""
from __future__ import annotations

from typing import Any

from modules_system.module_base import ModuleBase, ModuleMeta

# Relative imports с fallback для pytest (когда __init__.py импортируется
# как standalone модуль без parent package — importlib import mode).
try:
    from .config import ApiproxyConfig
    from .registry import MethodRegistry
    from .middleware import AuthMiddleware
    from .converter import call_method
    from .provider import ApiProxyProvider
except ImportError:
    # Fallback: импортируем модули напрямую через importlib
    import importlib
    import sys
    from pathlib import Path as _Path

    _pkg_dir = _Path(__file__).resolve().parent
    _parent = "apiproxy"

    def _lazy_import(module_name: str):
        full = f"{_parent}.{module_name}"
        if full not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                full, _pkg_dir / f"{module_name}.py",
            )
            mod = importlib.util.module_from_spec(spec)
            mod.__package__ = _parent
            sys.modules[full] = mod
            spec.loader.exec_module(mod)
        return sys.modules[full]

    ApiproxyConfig = _lazy_import("config").ApiproxyConfig  # type: ignore[assignment]
    MethodRegistry = _lazy_import("registry").MethodRegistry  # type: ignore[assignment]
    AuthMiddleware = _lazy_import("middleware").AuthMiddleware  # type: ignore[assignment]
    call_method = _lazy_import("converter").call_method  # type: ignore[assignment]
    ApiProxyProvider = _lazy_import("provider").ApiProxyProvider  # type: ignore[assignment]

__all__ = [
    "ApiProxyModule",
    "ApiProxyProvider",
    "ApiproxyConfig",
    "MethodRegistry",
    "AuthMiddleware",
    "call_method",
]

MODULE_VERSION = "1.0.0"

# Whitelist модулей по умолчанию
_DEFAULT_WHITELIST: list[str] = ["auth", "workspace", "llm"]


class ApiProxyModule(ModuleBase):
    """API Proxy модуль для Mia Framework.

    Прослойка между CLI и модулями:
    - Сбор метаданных методов из модулей (`@task(api=True)` → `_api_meta`)
    - Авторизация (AuthMiddleware)
    - Конвертация вызовов и нормализация ответов
    - Whitelist доступных модулей
    """

    @property
    def name(self) -> str:
        return "apiproxy"

    @property
    def version(self) -> str:
        return MODULE_VERSION

    @property
    def meta(self) -> ModuleMeta:
        return ModuleMeta(
            dependencies=["log", "auth", "workspace", "llm"],
            timeout_defaults={"call": 30.0, "list_api": 5.0},
        )

    def __init__(self, config: ApiproxyConfig | None = None) -> None:
        self._config = config or ApiproxyConfig.from_env()
        self._provider: ApiProxyProvider | None = None
        self._log = None

    def on_load(self, state: Any) -> None:
        """Инициализация модуля: создание провайдера и сбор методов."""
        self._log = state.log

        # Получаем AuthProvider из DI
        auth_provider = None
        try:
            from modules.auth.provider import AuthProvider
            auth_provider = state.services.resolve(AuthProvider)
        except Exception:
            self._log.warning("AuthProvider not found in DI — middleware will skip auth checks")

        # Создаём провайдер
        self._provider = ApiProxyProvider(
            config=self._config,
            auth_provider=auth_provider,
            log=self._log,
        )

        # Собираем методы из загруженных модулей
        self._collect_methods(state)

        # Регистрируем в DI
        state.services.register(ApiProxyProvider, self._provider)

        self._log.info(
            "apiproxy_module_loaded",
            version=self.version,
            modules=list(self._provider.registry.list_modules()),
        )

    def _collect_methods(self, state: Any) -> None:
        """Собрать методы из модулей, входящих в whitelist."""
        registry = self._provider.registry

        for module_name in self._config.whitelist:
            try:
                # Ищем провайдер модуля в DI
                provider_class = self._resolve_provider_class(module_name)
                if provider_class is None:
                    self._log.debug("provider_class_not_found", extra={"module": module_name})
                    continue

                provider = state.services.resolve(provider_class)
                if provider is None:
                    self._log.debug("provider_instance_not_found", extra={"module": module_name})
                    continue

                count = registry.collect_from_module(provider, module_name)
                self._log.info(
                    "methods_collected",
                    module=module_name,
                    count=count,
                )
            except Exception as e:
                self._log.warning(
                    "failed_to_collect_methods",
                    module=module_name,
                    error=str(e),
                )

    def _resolve_provider_class(self, module_name: str) -> type | None:
        """Разрешить класс провайдера по имени модуля.

        ImportError — ключ не кладём.
        """
        mapping: dict[str, type] = {}
        try:
            from modules.auth.provider import AuthProvider
            mapping["auth"] = AuthProvider
        except ImportError:
            pass
        try:
            from modules.llm.provider import LLMProvider
            mapping["llm"] = LLMProvider
        except ImportError:
            pass
        try:
            from modules.workspace.provider import WorkspaceProvider
            mapping["workspace"] = WorkspaceProvider
        except ImportError:
            pass
        return mapping.get(module_name)

    def on_unload(self) -> None:
        """Очистка ресурсов."""
        if self._provider:
            self._provider.registry.clear()
        self._log.info("apiproxy_module_unloaded")
        self._log = None
