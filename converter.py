"""Converter — вызов метода с валидацией аргументов и нормализацией ответа.

Конвертирует протокол: kwargs → вызов → нормализованный ответ.
"""
from __future__ import annotations

import inspect
from typing import Any

from .registry import MethodMeta

__all__ = ["call_method", "ApiError"]

_SELF_IGNORE_USER_ID = frozenset({
    "get_me",
    "update_me",
    "change_username",
    "set_avatar",
    "clear_avatar",
    "get_my_groups",
})

_STATUS_BY_CODE = {
    "INVALID_CREDENTIALS": 401,
    "LOCKED": 403,
    "DISABLED": 403,
    "REUSE_DETECTED": 401,
    "FORBIDDEN": 403,
    "PERMISSION_DENIED": 403,
    "NOT_FOUND": 404,
    "AUTH_ERROR": 401,
    "BOOTSTRAP_DONE": 409,
    "CSRF_HEADER": 403,
    "ORIGIN_MISMATCH": 403,
}


class ApiError(Exception):
    """Ошибка API-вызова."""

    def __init__(self, status_code: int, message: str, code: str = "") -> None:
        self.status_code = status_code
        self.code = code or f"ERROR_{status_code}"
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в dict для ответа."""
        return {
            "data": None,
            "error": {
                "code": self.code,
                "message": str(self),
                "status_code": self.status_code,
            },
        }


def _coerce_value(value: Any, expected_type: str) -> Any:
    """Привести значение к ожидаемому типу.

    Args:
        value: Исходное значение.
        expected_type: Ожидаемый тип (str, int, float, bool, list, dict).

    Returns:
        Приведённое значение.

    Raises:
        ValueError: Если приведение невозможно.
    """
    if value is None:
        return None

    type_map: dict[str, type] = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
    }

    target_type = type_map.get(expected_type)
    if target_type is None:
        return value

    # Если уже нужного типа — возвращаем как есть
    if isinstance(value, target_type):
        return value

    # Приведение
    try:
        return target_type(value)
    except (ValueError, TypeError) as e:
        raise ValueError(
            f"Cannot convert {value!r} to {expected_type}: {e}"
        ) from e


def _validate_args(
    meta: MethodMeta,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Валидация и приведение аргументов по метаданным метода.

    Args:
        meta: Метаданные метода.
        kwargs: Аргументы вызова.

    Returns:
        Валидированные и приведённые аргументы.

    Raises:
        ApiError: 400 — невалидные аргументы.
    """
    validated: dict[str, Any] = {}
    known_args = meta.args

    for arg_name, expected_type in known_args.items():
        if arg_name in kwargs:
            value = kwargs[arg_name]
            # Secret-поля — НЕ логируем
            try:
                validated[arg_name] = _coerce_value(value, expected_type)
            except ValueError as e:
                raise ApiError(400, f"Invalid argument '{arg_name}': {e}") from e
        elif arg_name not in kwargs:
            # Проверяем есть ли дефолт в сигнатуре функции
            sig = inspect.signature(meta.func)
            param = sig.parameters.get(arg_name)
            if param is not None and param.default is not inspect.Parameter.empty:
                # Есть дефолт — используем
                continue
            # Обязательный аргумент отсутствует
            raise ApiError(
                400, f"Missing required argument: '{arg_name}'"
            )

    # Дополнительные аргументы (не описанные в meta.args) — передаём как есть
    extra_keys = set(kwargs.keys()) - set(known_args.keys())
    for key in extra_keys:
        validated[key] = kwargs[key]

    return validated


async def call_method(
    registry: Any,
    middleware: Any,
    module_name: str,
    method_name: str,
    kwargs: dict[str, Any],
    token: str | None = None,
    log: Any | None = None,
) -> dict[str, Any]:
    """Выполнить API-метод с авторизацией и валидацией.

    Args:
        registry: MethodRegistry.
        middleware: AuthMiddleware.
        module_name: Имя модуля.
        method_name: Имя метода.
        kwargs: Аргументы вызова.
        token: Access token (опционально).

    Returns:
        {"data": result, "error": None} или {"data": None, "error": {...}}.
    """
    # 1. Поиск метода
    meta = registry.get_method(module_name, method_name)
    if meta is None:
        error = ApiError(404, f"Method not found: {module_name}.{method_name}")
        return error.to_dict()

    # 2. Авторизация
    try:
        authorized = await middleware.authorize(meta, token=token)
    except PermissionError as e:
        msg = str(e)
        if "401" in msg:
            error = ApiError(401, msg)
        else:
            error = ApiError(403, msg)
        return error.to_dict()

    # 3. Валидация аргументов
    try:
        validated_kwargs = _validate_args(meta, kwargs)
    except ApiError as e:
        return e.to_dict()

    _inject_session(authorized, validated_kwargs, meta)
    validated_kwargs = _kwargs_for_func(meta.func, validated_kwargs)

    # 4. Вызов метода
    try:
        result = await meta.func(**validated_kwargs)
    except ValueError as e:
        error = ApiError(400, str(e))
        return error.to_dict()
    except NotFoundError as e:
        error = ApiError(404, str(e))
        return error.to_dict()
    except PermissionError as e:
        error = ApiError(403, str(e))
        return error.to_dict()
    except Exception as e:
        coded = _from_coded_error(e)
        if coded is not None:
            return coded.to_dict()
        if log is not None:
            log.error("method_call_error", extra={"mod": module_name, "method": method_name, "error": str(e)})
        error = ApiError(500, f"Internal error: {e}")
        return error.to_dict()

    # 5. Нормализация ответа
    return {"data": result, "error": None}


def _ctx_user_id(ctx: Any) -> str | None:
    if ctx is None:
        return None
    if isinstance(ctx, dict):
        value = ctx.get("user_id")
        return str(value) if value else None
    value = getattr(ctx, "user_id", None)
    return str(value) if value else None


def _inject_session(authorized: Any, kwargs: dict[str, Any], meta: MethodMeta) -> None:
    """user_id из access JWT/cookie. Клиентский user_id на get_me/update_me игнор."""
    user_ctx = getattr(authorized, "user_ctx", None)
    session_id = _ctx_user_id(user_ctx)
    if session_id and meta.module == "auth" and meta.name in _SELF_IGNORE_USER_ID:
        kwargs.pop("user_id", None)
    if not session_id:
        return
    kwargs["_session_user_id"] = session_id


def _kwargs_for_func(func: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return kwargs
    if any(item.kind == inspect.Parameter.VAR_KEYWORD for item in params.values()):
        return kwargs
    # _session_user_id всегда в payload воркера — не режем по сигнатуре обёртки
    return {
        key: value
        for key, value in kwargs.items()
        if key in params or key == "_session_user_id"
    }


def _from_coded_error(exc: BaseException) -> ApiError | None:
    """AuthError.code → HTTP ≠ 500. Не глотаем INVALID_CREDENTIALS."""
    code = getattr(exc, "code", None)
    if not isinstance(code, str) or not code:
        return None
    status = _STATUS_BY_CODE.get(code)
    if status is None:
        return None
    return ApiError(status, str(exc), code)


class NotFoundError(Exception):
    """Запрашиваемая сущность не найдена."""
