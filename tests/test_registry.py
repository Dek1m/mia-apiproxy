"""Tests for MethodRegistry."""
from __future__ import annotations

import pytest

from apiproxy.registry import MethodRegistry, MethodMeta
from core.task_decorator import task


class TestRegistryRegister:
    def test_register_basic(self):
        reg = MethodRegistry()
        func = lambda: None
        func._api_meta = {
            "name": "test_method",
            "description": "Test",
            "args": {"x": "int"},
            "return_type": "int",
            "public": True,
            "required_permission": None,
        }
        reg.register("mymodule", "test_method", func._api_meta, func)
        meta = reg.get_method("mymodule", "test_method")
        assert meta is not None
        assert meta.name == "test_method"
        assert meta.public is True

    def test_register_duplicate_raises(self):
        reg = MethodRegistry()
        func = lambda: None
        func._api_meta = {"name": "dup", "args": {}, "public": True}
        reg.register("m", "dup", func._api_meta, func)
        with pytest.raises(ValueError, match="Duplicate method"):
            reg.register("m", "dup", func._api_meta, func)


class TestRegistryCollect:
    def test_collect_from_module(self, fake_module):
        reg = MethodRegistry()
        count = reg.collect_from_module(fake_module, "fake")
        assert count >= 5
        assert reg.has_module("fake")

    def test_collect_only_api_true(self):
        class Mixed:
            @task(type="cpu")
            async def internal(self) -> None:
                pass

            @task(type="cpu", api=True)
            async def exported(self) -> None:
                pass

        reg = MethodRegistry()
        count = reg.collect_from_module(Mixed(), "test")
        assert count == 1
        assert reg.get_method("test", "exported") is not None
        assert reg.get_method("test", "internal") is None


class TestRegistryList:
    def test_list_modules(self, fake_module):
        reg = MethodRegistry()
        reg.collect_from_module(fake_module, "auth")
        modules = reg.list_modules()
        assert "auth" in modules

    def test_list_methods(self, fake_module):
        reg = MethodRegistry()
        reg.collect_from_module(fake_module, "auth")
        methods = reg.list_methods("auth")
        names = [m.name for m in methods]
        assert "login" in names
        assert "get_me" in names

    def test_list_all_methods(self, fake_module):
        reg = MethodRegistry()
        reg.collect_from_module(fake_module, "auth")
        all_methods = reg.list_all_methods()
        assert len(all_methods) >= 5

    def test_get_nonexistent(self):
        reg = MethodRegistry()
        assert reg.get_method("nope", "nope") is None

    def test_clear(self, fake_module):
        reg = MethodRegistry()
        reg.collect_from_module(fake_module, "auth")
        assert len(reg.list_modules()) > 0
        reg.clear()
        assert len(reg.list_modules()) == 0
