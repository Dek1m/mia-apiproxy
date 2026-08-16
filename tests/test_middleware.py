"""Tests for AuthMiddleware."""
from __future__ import annotations

import pytest

from apiproxy.middleware import AuthMiddleware, AuthorizedCall
from apiproxy.registry import MethodMeta
from modules.auth.provider import UserContext


def _make_meta(
    public: bool = False,
    required_permission: str | None = None,
) -> MethodMeta:
    return MethodMeta(
        name="test",
        description="test method",
        args={},
        return_type=None,
        public=public,
        required_permission=required_permission,
        func=lambda: None,
        module="test",
    )


@pytest.mark.asyncio
class TestMiddlewarePublic:
    async def test_public_method_skips_auth(self):
        mw = AuthMiddleware(auth_provider=None)
        meta = _make_meta(public=True)
        result = await mw.authorize(meta, token=None)
        assert result.user_ctx is None
        assert result.meta is meta


@pytest.mark.asyncio
class TestMiddlewareNoToken:
    async def test_no_token_raises_401(self):
        mw = AuthMiddleware(auth_provider=None)
        meta = _make_meta(public=False)
        with pytest.raises(PermissionError, match="401"):
            await mw.authorize(meta, token=None)


@pytest.mark.asyncio
class TestMiddlewareInvalidToken:
    async def test_invalid_token_raises_401(self, fake_auth_provider):
        mw = AuthMiddleware(auth_provider=fake_auth_provider)
        meta = _make_meta(public=False)
        with pytest.raises(PermissionError, match="401"):
            await mw.authorize(meta, token="bad-token")


@pytest.mark.asyncio
class TestMiddlewareValidToken:
    async def test_valid_token_no_permission_required(self, fake_auth_provider):
        user_ctx = UserContext(user_id="u1", username="admin", perms_version=1)
        fake_auth_provider.register_token("good-token", user_ctx)
        mw = AuthMiddleware(auth_provider=fake_auth_provider)
        meta = _make_meta(public=False, required_permission=None)
        result = await mw.authorize(meta, token="good-token")
        assert result.user_ctx is not None
        assert result.user_ctx.user_id == "u1"

    async def test_valid_token_with_permission(self, fake_auth_provider):
        user_ctx = UserContext(user_id="u1", username="admin", perms_version=1)
        fake_auth_provider.register_token("good-token", user_ctx)
        fake_auth_provider.set_permissions("u1", {"users:read"})
        mw = AuthMiddleware(auth_provider=fake_auth_provider)
        meta = _make_meta(public=False, required_permission="users:read")
        result = await mw.authorize(meta, token="good-token")
        assert result.user_ctx.user_id == "u1"


@pytest.mark.asyncio
class TestMiddlewareForbidden:
    async def test_no_permission_raises_403(self, fake_auth_provider):
        user_ctx = UserContext(user_id="u1", username="admin", perms_version=1)
        fake_auth_provider.register_token("good-token", user_ctx)
        mw = AuthMiddleware(auth_provider=fake_auth_provider)
        meta = _make_meta(public=False, required_permission="admin:write")
        with pytest.raises(PermissionError, match="403"):
            await mw.authorize(meta, token="good-token")


@pytest.mark.asyncio
class TestMiddlewareWildcard:
    async def test_wildcard_star_allows_any(self, fake_auth_provider):
        user_ctx = UserContext(user_id="u1", username="admin", perms_version=1)
        fake_auth_provider.register_token("good-token", user_ctx)
        fake_auth_provider.set_permissions("u1", {"*:*"})
        mw = AuthMiddleware(auth_provider=fake_auth_provider)
        meta = _make_meta(public=False, required_permission="anything:goes")
        result = await mw.authorize(meta, token="good-token")
        assert result.user_ctx is not None

    async def test_wildcard_resource(self, fake_auth_provider):
        user_ctx = UserContext(user_id="u1", username="admin", perms_version=1)
        fake_auth_provider.register_token("good-token", user_ctx)
        fake_auth_provider.set_permissions("u1", {"users:*"})
        mw = AuthMiddleware(auth_provider=fake_auth_provider)
        meta = _make_meta(public=False, required_permission="users:delete")
        result = await mw.authorize(meta, token="good-token")
        assert result.user_ctx is not None


@pytest.mark.asyncio
class TestMiddlewareNoProvider:
    async def test_no_provider_skips_check(self):
        mw = AuthMiddleware(auth_provider=None)
        meta = _make_meta(public=False)
        result = await mw.authorize(meta, token="any-token")
        assert result.user_ctx is None
