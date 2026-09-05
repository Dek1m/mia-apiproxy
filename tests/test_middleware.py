"""Tests for AuthMiddleware."""
from __future__ import annotations

import pytest

from apiproxy.middleware import AuthMiddleware, AuthUnavailableError, AuthorizedCall
from apiproxy.registry import MethodMeta
from modules.auth.provider import UserContext


def _make_meta(
    public: bool = False,
    required_permission: str | None = None,
    name: str = "test",
    module: str = "test",
) -> MethodMeta:
    return MethodMeta(
        name=name,
        description="test method",
        args={},
        return_type=None,
        public=public,
        required_permission=required_permission,
        func=lambda: None,
        module=module,
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
    async def test_profile_self_any_authenticated(self, fake_auth_provider):
        user_ctx = UserContext(user_id="u1", username="plain", perms_version=1)
        fake_auth_provider.register_token("good-token", user_ctx)
        mw = AuthMiddleware(auth_provider=fake_auth_provider)
        meta = _make_meta(public=False, required_permission="profile:self")
        result = await mw.authorize(meta, token="good-token")
        assert result.user_ctx.user_id == "u1"

    async def test_valid_token_no_permission_required(self, fake_auth_provider):
        user_ctx = UserContext(user_id="u1", username="admin", perms_version=1)
        fake_auth_provider.register_token("good-token", user_ctx)
        mw = AuthMiddleware(auth_provider=fake_auth_provider)
        meta = _make_meta(public=False, required_permission=None)
        result = await mw.authorize(meta, token="good-token")
        assert result.user_ctx is not None
        assert result.user_ctx.user_id == "u1"

    async def test_dict_user_ctx_from_worker(self, fake_auth_provider):
        fake_auth_provider.register_token("good-token", {"user_id": "u1", "username": "admin"})
        fake_auth_provider.set_permissions("u1", {"llm:config"})
        mw = AuthMiddleware(auth_provider=fake_auth_provider)
        meta = _make_meta(public=False, required_permission="llm:config")
        result = await mw.authorize(meta, token="good-token")
        assert result.user_ctx["user_id"] == "u1"

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
class TestMiddlewareCookieCredential:
    async def test_refresh_without_access_token(self):
        mw = AuthMiddleware(auth_provider=None)
        meta = _make_meta(public=False, name="refresh_token", module="auth")
        result = await mw.authorize(meta, token=None)
        assert result.user_ctx is None

    async def test_logout_without_access_token(self):
        mw = AuthMiddleware(auth_provider=None)
        meta = _make_meta(public=False, name="logout", module="auth")
        result = await mw.authorize(meta, token=None)
        assert result.user_ctx is None


@pytest.mark.asyncio
class TestMiddlewareNoProvider:
    async def test_no_provider_fail_closed(self, monkeypatch):
        """Без auth_provider валидация невозможна → AuthUnavailableError (503)."""
        monkeypatch.delenv("MIA_DEV_NO_AUTH", raising=False)
        mw = AuthMiddleware(auth_provider=None)
        meta = _make_meta(public=False)
        with pytest.raises(AuthUnavailableError, match="503"):
            await mw.authorize(meta, token="any-token")

    async def test_no_provider_no_token_still_401(self, monkeypatch):
        """Порядок проверок: отсутствие токена — 401 до 503."""
        monkeypatch.delenv("MIA_DEV_NO_AUTH", raising=False)
        mw = AuthMiddleware(auth_provider=None)
        meta = _make_meta(public=False)
        with pytest.raises(PermissionError, match="401"):
            await mw.authorize(meta, token=None)

    async def test_dev_no_auth_bypass_with_error_log(self, monkeypatch):
        """MIA_DEV_NO_AUTH=1 — обход, но ERROR в лог на каждый запрос."""
        monkeypatch.setenv("MIA_DEV_NO_AUTH", "1")

        class _Log:
            def __init__(self):
                self.records = []

            def error(self, message, **kwargs):
                self.records.append((message, kwargs))

        log = _Log()
        mw = AuthMiddleware(auth_provider=None, log=log)
        meta = _make_meta(public=False, module="llm", name="run_pipeline")
        result = await mw.authorize(meta, token="any-token")
        assert result.user_ctx is None
        assert log.records == [
            ("dev_no_auth_bypass", {"extra": {"mod": "llm", "method": "run_pipeline"}}),
        ]

    async def test_public_method_unaffected_by_missing_provider(self, monkeypatch):
        """Public-методы проходят без провайдера и без флага."""
        monkeypatch.delenv("MIA_DEV_NO_AUTH", raising=False)
        mw = AuthMiddleware(auth_provider=None)
        meta = _make_meta(public=True)
        result = await mw.authorize(meta, token=None)
        assert result.user_ctx is None
