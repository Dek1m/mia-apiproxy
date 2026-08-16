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
