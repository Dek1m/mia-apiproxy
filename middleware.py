"""AuthMiddleware — проверка авторизации перед вызовом метода.

НЕ привязан к HTTP — чистая логика авторизации.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .registry import MethodMeta

__all__ = ["AuthMiddleware", "AuthorizedCall"]

# Живой access JWT не нужен: credential проверит provider (cookie / kwargs)
_COOKIE_CREDENTIAL = frozenset({
    ("auth", "refresh_token"),
    ("auth", "logout"),
})


@dataclass
class AuthorizedCall:
    """Результат авторизации — контекст для вызова метода."""

    user_ctx: Any | None
    meta: MethodMeta


class AuthMiddleware:
    """Middleware авторизации.

    Проверяет:
    - public методы → пропуск
    - Токен обязателен (иначе 401)
    - Валидация токена (иначе 401)
    - Проверка permissions (иначе 403)
    """

    def __init__(
        self,
        auth_provider: Any | None = None,
        log: Any | None = None,
    ) -> None:
        self._auth_provider = auth_provider
        self._log = log

    async def authorize(
        self,
        meta: MethodMeta,
        token: str | None = None,
        **ctx: Any,
    ) -> AuthorizedCall:
        """Проверить авторизацию для вызова метода.

        Args:
            meta: Метаданные метода.
            token: Access token (может быть None для public методов).
            **ctx: Дополнительный контекст.

        Returns:
            AuthorizedCall с контекстом пользователя.

        Raises:
            PermissionError: 401 — нет токена или токен невалиден.
            PermissionError: 403 — нет нужного разрешения.
        """
        # Public метод — пропуск
        if meta.public:
            return AuthorizedCall(user_ctx=None, meta=meta)

        # refresh/logout: не требуем живой access JWT
        if (meta.module, meta.name) in _COOKIE_CREDENTIAL:
            return AuthorizedCall(user_ctx=None, meta=meta)

        # Токен обязателен
        if not token:
            raise PermissionError("Authentication required (401)")

        # Нет auth_provider — пропускаем проверку (dev mode)
        if self._auth_provider is None:
            if self._log is not None:
                self._log.warning("No auth_provider — skipping auth check")
            return AuthorizedCall(user_ctx=None, meta=meta)

        # Валидация токена
        user_ctx = await self._auth_provider.validate_token(token)
        if user_ctx is None:
            raise PermissionError("Invalid or expired token (401)")

        # profile:self — любой валидный user_ctx, не users:read
        if meta.required_permission and meta.required_permission != "profile:self":
            user_id = _ctx_user_id(user_ctx)
            if not user_id:
                raise PermissionError("Invalid or expired token (401)")
            has_perm = await self._auth_provider.check_permission(
                user_id, meta.required_permission,
            )
            if not has_perm:
                if self._log is not None:
                    self._log.warning(
                        "permission_denied",
                        extra={
                            "user_id": user_id,
                            "permission": meta.required_permission,
                            "module": meta.module,
                            "method": meta.name,
                        },
                    )
                raise PermissionError(
                    f"Permission denied: {meta.required_permission} (403)"
                )

        return AuthorizedCall(user_ctx=user_ctx, meta=meta)


def _ctx_user_id(ctx: Any) -> str | None:
    """JWT/celery может отдать UserContext или dict."""
    if ctx is None:
        return None
    if isinstance(ctx, dict):
        value = ctx.get("user_id")
        return str(value) if value else None
    value = getattr(ctx, "user_id", None)
    return str(value) if value else None
