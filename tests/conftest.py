"""Conftest для apiproxy тестов — динамическая загрузка модуля apiproxy."""
from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from modules.auth.provider import UserContext

# ── Динамическая загрузка модуля apiproxy ──────────────

_MODULE_DIR = Path(__file__).resolve().parent.parent

# Создаём фейковый пакет-родитель для относительных импортов
_fake_package = types.ModuleType("apiproxy")
_fake_package.__path__ = [str(_MODULE_DIR)]  # type: ignore[attr-defined]
_fake_package.__package__ = "apiproxy"
sys.modules["apiproxy"] = _fake_package


def _load_submodule(name: str) -> types.ModuleType:
    """Загрузить подмодуль из apiproxy директории."""
    file_path = _MODULE_DIR / f"{name}.py"
    if not file_path.exists():
        raise FileNotFoundError(f"Module file not found: {file_path}")

    full_name = f"apiproxy.{name}"
    spec = importlib.util.spec_from_file_location(
        full_name, file_path,
        submodule_search_locations=[],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create spec for {full_name}")

    module = importlib.util.module_from_spec(spec)
    module.__package__ = "apiproxy"
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


# Загружаем модули в правильном порядке зависимостей
_config = _load_submodule("config")
_registry = _load_submodule("registry")
_middleware = _load_submodule("middleware")
_converter = _load_submodule("converter")
_provider = _load_submodule("provider")

# Экспортируем для тестов
from apiproxy.config import ApiproxyConfig  # noqa: E402
from apiproxy.registry import MethodRegistry, MethodMeta  # noqa: E402
from apiproxy.middleware import AuthMiddleware, AuthorizedCall  # noqa: E402
from apiproxy.converter import (  # noqa: E402
    call_method,
    ApiError,
    _coerce_value,
    _validate_args,
    NotFoundError,
)
from apiproxy.provider import ApiProxyProvider  # noqa: E402


# ── Фейковый AuthProvider ──────────────────────────────


class FakeAuthProvider:
    """Фейковый auth_provider для тестов — без БД."""

    def __init__(self) -> None:
        self._tokens: dict[str, Any] = {}
        self._permissions: dict[str, set[str]] = {}

    def register_token(self, token: str, user_ctx: Any) -> None:
        self._tokens[token] = user_ctx

    def set_permissions(self, user_id: str, perms: set[str]) -> None:
        self._permissions[user_id] = perms

    async def validate_token(self, access_token: str) -> UserContext | None:
        return self._tokens.get(access_token)

    async def check_permission(self, user_id: str, permission: str) -> bool:
        perms = self._permissions.get(user_id, set())
        if "*:*" in perms:
            return True
        if permission in perms:
            return True
        if ":" in permission:
            resource = permission.split(":")[0]
            if f"{resource}:*" in perms:
                return True
        return False


# ── Фейковый модуль с методами ────────────────────────


class FakeModule:
    """Фейковый модуль с `_api_meta` вручную — converter зовёт in-process, без @task."""

    async def login(self, username: str, password: str) -> dict[str, Any]:
        return {"access_token": "fake-token", "user_id": "user-1"}

    login._api_meta = {
        "name": "login",
        "description": "Вход в систему",
        "args": {"username": "str", "password": "str"},
        "return_type": "dict",
        "public": True,
        "required_permission": None,
    }

    async def get_me(self) -> dict[str, Any]:
        return {"id": "user-1", "username": "admin"}

    get_me._api_meta = {
        "name": "get_me",
        "description": "Получить данные текущего пользователя",
        "args": {},
        "return_type": "dict",
        "public": False,
        "required_permission": "users:read",
    }

    async def create_user(
        self, username: str, password: str, email: str = "",
    ) -> dict[str, Any]:
        return {"id": "new-user", "username": username}

    create_user._api_meta = {
        "name": "create_user",
        "description": "Создать пользователя",
        "args": {"username": "str", "password": "str", "email": "str"},
        "return_type": "dict",
        "public": False,
        "required_permission": "users:create",
    }

    async def secret_action(self, token: str, api_key: str) -> str:
        return f"done:{token[:4]}"

    secret_action._api_meta = {
        "name": "secret_action",
        "description": "Действие с secret полем",
        "args": {"token": "str", "api_key": "str"},
        "return_type": "str",
        "public": False,
        "required_permission": None,
    }

    async def typed_method(
        self, count: int, ratio: float, flag: bool,
    ) -> dict[str, Any]:
        return {"count": count, "ratio": ratio, "flag": flag}

    typed_method._api_meta = {
        "name": "typed_method",
        "description": "Метод с разными типами",
        "args": {"count": "int", "ratio": "float", "flag": "bool"},
        "return_type": "dict",
        "public": True,
        "required_permission": None,
    }

    async def error_method(self, mode: str) -> str:
        if mode == "value":
            raise ValueError("bad value")
        if mode == "not_found":
            raise NotFoundError("entity not found")
        if mode == "permission":
            raise PermissionError("no access")
        return "ok"

    error_method._api_meta = {
        "name": "error_method",
        "description": "Метод который бросает ошибки",
        "args": {"mode": "str"},
        "return_type": "str",
        "public": True,
        "required_permission": None,
    }


# ── Фикстуры ────────────────────────────────────────────


@pytest.fixture
def fake_auth_provider() -> FakeAuthProvider:
    return FakeAuthProvider()


@pytest.fixture
def fake_module() -> FakeModule:
    return FakeModule()
