"""Tests for ApiProxyProvider — call, registry, list_api."""
from __future__ import annotations

import pytest

from apiproxy.provider import ApiProxyProvider
from apiproxy.config import ApiproxyConfig
from apiproxy.registry import MethodRegistry
from modules.auth.provider import UserContext


@pytest.fixture
def provider(fake_module, fake_auth_provider) -> ApiProxyProvider:
    config = ApiproxyConfig(whitelist=["fake", "auth"])
    p = ApiProxyProvider(config=config, auth_provider=fake_auth_provider)
    p.registry.collect_from_module(fake_module, "fake")
    return p


@pytest.mark.asyncio
class TestProviderCall:
    async def test_registry_ok(self, provider):
        result = await provider.call(
            "fake", "typed_method",
            {"count": 1, "ratio": 1.0, "flag": False},
        )
        assert result["error"] is None
        assert result["data"]["count"] == 1

    async def test_unknown_module_is_404_not_whitelist(self, provider):
        result = await provider.call("secret_module", "do_thing", {})
        assert result["error"] is not None
        assert result["error"]["status_code"] == 404
        assert "whitelist" not in result["error"]["message"]

    async def test_call_ignores_config_whitelist(self, fake_module, fake_auth_provider):
        config = ApiproxyConfig(whitelist=["auth"])
        p = ApiProxyProvider(config=config, auth_provider=fake_auth_provider)
        p.registry.collect_from_module(fake_module, "fake")
        result = await p.call(
            "fake", "typed_method",
            {"count": 2, "ratio": 0.5, "flag": True},
        )
        assert result["error"] is None
        assert result["data"]["count"] == 2

    async def test_method_not_found(self, provider):
        result = await provider.call("fake", "nonexistent", {})
        assert result["error"] is not None
        assert result["error"]["status_code"] == 404

    async def test_auth_required_no_token(self, provider):
        result = await provider.call("fake", "get_me", {})
        assert result["error"] is not None
        assert result["error"]["status_code"] == 401

    async def test_auth_ok(self, provider, fake_auth_provider):
        user_ctx = UserContext(user_id="u1", username="admin", perms_version=1)
        fake_auth_provider.register_token("tok", user_ctx)
        fake_auth_provider.set_permissions("u1", {"users:read"})
        result = await provider.call("fake", "get_me", {}, token="tok")
        assert result["error"] is None
        assert result["data"]["username"] == "admin"

    async def test_auth_no_permission(self, provider, fake_auth_provider):
        user_ctx = UserContext(user_id="u1", username="admin", perms_version=1)
        fake_auth_provider.register_token("tok", user_ctx)
        result = await provider.call("fake", "get_me", {}, token="tok")
        assert result["error"] is not None
        assert result["error"]["status_code"] == 403


class TestProviderListApi:
    def test_list_api_all(self, provider):
        methods = provider.list_api()
        names = [m["name"] for m in methods]
        assert "login" in names
        assert "get_me" in names

    def test_list_api_filtered(self, provider):
        methods = provider.list_api(module_name="fake")
        names = [m["name"] for m in methods]
        assert "login" in names
        assert all(m["module"] == "fake" for m in methods)

    def test_list_api_empty_module(self, provider):
        methods = provider.list_api(module_name="nonexistent")
        assert methods == []


class TestCallListApiNotTasks:
    """call / list_api — не @task, converter зовёт in-process."""

    def test_call_has_no_task_type(self) -> None:
        assert not hasattr(ApiProxyProvider.call, "_task_type")
        assert not hasattr(ApiProxyProvider.call, "_api_meta")

    def test_list_api_has_no_task_type(self) -> None:
        assert not hasattr(ApiProxyProvider.list_api, "_task_type")
        assert not hasattr(ApiProxyProvider.list_api, "_api_meta")
