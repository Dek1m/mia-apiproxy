"""Tests for Converter — валидация, ошибки, нормализация."""
from __future__ import annotations

import pytest

from apiproxy.converter import (
    call_method,
    ApiError,
    _coerce_value,
    _validate_args,
    NotFoundError,
)
from apiproxy.middleware import AuthMiddleware
from apiproxy.registry import MethodRegistry, MethodMeta


class TestCoerceValue:
    def test_str_to_str(self):
        assert _coerce_value("hello", "str") == "hello"

    def test_int_to_int(self):
        assert _coerce_value(42, "int") == 42

    def test_str_to_int(self):
        assert _coerce_value("42", "int") == 42

    def test_int_to_str(self):
        assert _coerce_value(42, "str") == "42"

    def test_str_to_float(self):
        assert _coerce_value("3.14", "float") == pytest.approx(3.14)

    def test_int_to_bool(self):
        assert _coerce_value(1, "bool") is True
        assert _coerce_value(0, "bool") is False

    def test_none_passthrough(self):
        assert _coerce_value(None, "str") is None

    def test_invalid_conversion(self):
        with pytest.raises(ValueError, match="Cannot convert"):
            _coerce_value("not_a_number", "int")

    def test_unknown_type(self):
        assert _coerce_value("hello", "unknown") == "hello"


class TestValidateArgs:
    def test_valid_args(self):
        meta = MethodMeta(
            name="test", description="", args={"x": "int", "y": "str"},
            return_type=None, public=True, required_permission=None,
            func=lambda: None, module="m",
        )
        result = _validate_args(meta, {"x": 1, "y": "hello"})
        assert result == {"x": 1, "y": "hello"}

    def test_type_coercion(self):
        meta = MethodMeta(
            name="test", description="", args={"x": "int"},
            return_type=None, public=True, required_permission=None,
            func=lambda: None, module="m",
        )
        result = _validate_args(meta, {"x": "42"})
        assert result == {"x": 42}

    def test_missing_required(self):
        meta = MethodMeta(
            name="test", description="", args={"x": "int"},
            return_type=None, public=True, required_permission=None,
            func=lambda: None, module="m",
        )
        with pytest.raises(ApiError) as exc_info:
            _validate_args(meta, {})
        assert exc_info.value.status_code == 400
        assert "Missing required" in str(exc_info.value)

    def test_extra_args_passed(self):
        meta = MethodMeta(
            name="test", description="", args={"x": "int"},
            return_type=None, public=True, required_permission=None,
            func=lambda: None, module="m",
        )
        result = _validate_args(meta, {"x": 1, "extra": "value"})
        assert result == {"x": 1, "extra": "value"}

    def test_invalid_type_raises_400(self):
        meta = MethodMeta(
            name="test", description="", args={"x": "int"},
            return_type=None, public=True, required_permission=None,
            func=lambda: None, module="m",
        )
        with pytest.raises(ApiError) as exc_info:
            _validate_args(meta, {"x": "not_int"})
        assert exc_info.value.status_code == 400


class TestCallMethod:
    @pytest.mark.asyncio
    async def test_not_found(self):
        reg = MethodRegistry()
        mw = AuthMiddleware()
        result = await call_method(reg, mw, "nope", "nope", {})
        assert result["error"] is not None
        assert result["error"]["status_code"] == 404

    @pytest.mark.asyncio
    async def test_public_method_calls(self, fake_module):
        reg = MethodRegistry()
        reg.collect_from_module(fake_module, "fake")
        mw = AuthMiddleware()
        result = await call_method(
            reg, mw, "fake", "typed_method",
            {"count": 5, "ratio": 1.5, "flag": True},
        )
        assert result["error"] is None
        assert result["data"]["count"] == 5
        assert result["data"]["ratio"] == pytest.approx(1.5)
        assert result["data"]["flag"] is True

    @pytest.mark.asyncio
    async def test_value_error_returns_400(self, fake_module):
        reg = MethodRegistry()
        reg.collect_from_module(fake_module, "fake")
        mw = AuthMiddleware()
        result = await call_method(
            reg, mw, "fake", "error_method", {"mode": "value"},
        )
        assert result["error"] is not None
        assert result["error"]["status_code"] == 400

    @pytest.mark.asyncio
    async def test_not_found_error_returns_404(self, fake_module):
        reg = MethodRegistry()
        reg.collect_from_module(fake_module, "fake")
        mw = AuthMiddleware()
        result = await call_method(
            reg, mw, "fake", "error_method", {"mode": "not_found"},
        )
        assert result["error"] is not None
        assert result["error"]["status_code"] == 404

    @pytest.mark.asyncio
    async def test_permission_error_returns_403(self, fake_module):
        reg = MethodRegistry()
        reg.collect_from_module(fake_module, "fake")
        mw = AuthMiddleware()
        result = await call_method(
            reg, mw, "fake", "error_method", {"mode": "permission"},
        )
        assert result["error"] is not None
        assert result["error"]["status_code"] == 403

    @pytest.mark.asyncio
    async def test_auth_required_no_token(self, fake_module):
        reg = MethodRegistry()
        reg.collect_from_module(fake_module, "fake")
        mw = AuthMiddleware()
        result = await call_method(
            reg, mw, "fake", "get_me", {},
        )
        assert result["error"] is not None
        assert result["error"]["status_code"] == 401

    @pytest.mark.asyncio
    async def test_invalid_credentials_is_401_not_500(self):
        from modules.auth.provider import InvalidCredentialsError

        async def boom() -> None:
            raise InvalidCredentialsError()

        reg = MethodRegistry()
        reg.register(
            "auth",
            "login",
            {
                "name": "login",
                "description": "",
                "args": {},
                "return_type": "dict",
                "public": True,
                "required_permission": None,
            },
            boom,
        )
        mw = AuthMiddleware()
        result = await call_method(reg, mw, "auth", "login", {})
        assert result["error"] is not None
        assert result["error"]["status_code"] == 401
        assert result["error"]["code"] == "INVALID_CREDENTIALS"

    @pytest.mark.asyncio
    async def test_validation_code_is_400_not_500(self):
        class DomainError(Exception):
            def __init__(self) -> None:
                self.code = "VALIDATION"
                self.human = "Invalid page cursor"
                super().__init__("invalid cursor")

        async def boom() -> None:
            raise DomainError()

        reg = MethodRegistry()
        reg.register(
            "notification",
            "list",
            {
                "name": "list",
                "description": "",
                "args": {},
                "return_type": "dict",
                "public": True,
                "required_permission": None,
            },
            boom,
        )
        mw = AuthMiddleware()
        result = await call_method(reg, mw, "notification", "list", {})
        assert result["error"] is not None
        assert result["error"]["status_code"] == 400
        assert result["error"]["code"] == "VALIDATION"
        assert result["error"]["message"] == "Invalid page cursor"

    @pytest.mark.asyncio
    async def test_query_failed_is_500_with_human(self):
        class DomainError(Exception):
            def __init__(self) -> None:
                self.code = "QUERY_FAILED"
                self.human = "Could not load notifications"
                super().__init__("could not determine data type of parameter $2")

        async def boom() -> None:
            raise DomainError()

        reg = MethodRegistry()
        reg.register(
            "notification",
            "list",
            {
                "name": "list",
                "description": "",
                "args": {},
                "return_type": "dict",
                "public": True,
                "required_permission": None,
            },
            boom,
        )
        mw = AuthMiddleware()
        result = await call_method(reg, mw, "notification", "list", {})
        assert result["error"] is not None
        assert result["error"]["status_code"] == 500
        assert result["error"]["code"] == "QUERY_FAILED"
        assert result["error"]["message"] == "Could not load notifications"

    @pytest.mark.asyncio
    async def test_not_implemented_is_501_not_500(self):
        class DomainError(Exception):
            def __init__(self) -> None:
                self.code = "NOT_IMPLEMENTED"
                self.human = "Not implemented yet"
                super().__init__("Not implemented yet")

        async def boom() -> None:
            raise DomainError()

        reg = MethodRegistry()
        reg.register(
            "system",
            "modules_reload",
            {
                "name": "modules_reload",
                "description": "",
                "args": {"name": "str"},
                "return_type": "dict",
                "public": True,
                "required_permission": None,
            },
            boom,
        )
        mw = AuthMiddleware()
        result = await call_method(reg, mw, "system", "modules_reload", {"name": "fs"})
        assert result["error"] is not None
        assert result["error"]["status_code"] == 501
        assert result["error"]["code"] == "NOT_IMPLEMENTED"
        assert result["error"]["message"] == "Not implemented yet"

    @pytest.mark.asyncio
    async def test_unknown_kwargs_dropped_not_500(self):
        async def list_fn(
            limit: int = 50,
            cursor: str = "",
            _session_user_id: str | None = None,
        ) -> dict[str, object]:
            return {"items": [], "next_cursor": None}

        list_fn._api_meta = {  # type: ignore[attr-defined]
            "name": "list",
            "description": "",
            "args": {"limit": "int", "cursor": "str"},
            "return_type": "dict",
            "public": True,
            "required_permission": None,
        }
        reg = MethodRegistry()
        reg.register("notification", "list", list_fn._api_meta, list_fn)
        mw = AuthMiddleware()
        result = await call_method(
            reg,
            mw,
            "notification",
            "list",
            {"limit": 50, "unread_first": True, "before": "legacy"},
        )
        assert result["error"] is None
        assert result["data"]["items"] == []
        assert result["data"]["next_cursor"] is None


class _CaptureLog:
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def warning(self, message: str, **kwargs) -> None:
        self.records.append(("warning", message, kwargs.get("extra", {})))

    def error(self, message: str, **kwargs) -> None:
        self.records.append(("error", message, kwargs.get("extra", {})))


def _secret_registry() -> MethodRegistry:
    async def secret() -> dict[str, str]:
        return {"ok": "yes"}

    reg = MethodRegistry()
    reg.register(
        "llm",
        "run_pipeline",
        {
            "name": "run_pipeline",
            "description": "",
            "args": {},
            "return_type": "dict",
            "public": False,
            "required_permission": "llm:chat",
        },
        secret,
    )
    return reg


class TestAuthzDenied:
    @pytest.mark.asyncio
    async def test_no_auth_provider_is_503_not_bypass(self, monkeypatch):
        """Fail-closed: без auth_provider защищённый метод → 503 AUTH_UNAVAILABLE."""
        monkeypatch.delenv("MIA_DEV_NO_AUTH", raising=False)
        reg = _secret_registry()
        mw = AuthMiddleware()
        log = _CaptureLog()
        result = await call_method(reg, mw, "llm", "run_pipeline", {}, token="tok", log=log)
        assert result["error"] is not None
        assert result["error"]["status_code"] == 503
        assert result["error"]["code"] == "AUTH_UNAVAILABLE"
        assert ("warning", "authz_denied", {"mod": "llm", "method": "run_pipeline", "code": "AUTH_UNAVAILABLE"}) in log.records

    @pytest.mark.asyncio
    async def test_no_token_logs_authz_denied_unauthenticated(self):
        reg = _secret_registry()
        mw = AuthMiddleware()
        log = _CaptureLog()
        result = await call_method(reg, mw, "llm", "run_pipeline", {}, token=None, log=log)
        assert result["error"] is not None
        assert result["error"]["status_code"] == 401
        assert ("warning", "authz_denied", {"mod": "llm", "method": "run_pipeline", "code": "UNAUTHENTICATED"}) in log.records

    @pytest.mark.asyncio
    async def test_method_permission_error_logs_authz_denied(self, fake_module):
        reg = MethodRegistry()
        reg.collect_from_module(fake_module, "fake")
        mw = AuthMiddleware()
        log = _CaptureLog()
        result = await call_method(
            reg, mw, "fake", "error_method", {"mode": "permission"}, log=log,
        )
        assert result["error"]["status_code"] == 403
        assert any(
            message == "authz_denied" and extra.get("code") == "PERMISSION_DENIED"
            for _, message, extra in log.records
        )
