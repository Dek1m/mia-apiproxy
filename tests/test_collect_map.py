"""Collect с module._provider, без mapping классов."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def _load_api_proxy_module() -> type:
    init_path = Path(__file__).resolve().parent.parent / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "apiproxy_collect_map_mod",
        init_path,
        submodule_search_locations=[str(init_path.parent)],
    )
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load apiproxy __init__.py")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "apiproxy"
    spec.loader.exec_module(module)
    return module.ApiProxyModule


class _FakeProvider:
    async def ping(self) -> str:
        return "ok"

    ping._api_meta = {
        "name": "ping",
        "description": "ping",
        "args": {},
        "return_type": "str",
        "public": True,
        "required_permission": None,
    }


class _Loaded:
    def __init__(self, mapping: dict[str, Any]) -> None:
        self._mapping = mapping

    def list_all(self) -> list[str]:
        return list(self._mapping)

    def get(self, name: str) -> Any:
        return self._mapping.get(name)


def test_no_resolve_provider_class() -> None:
    cls = _load_api_proxy_module()
    assert not hasattr(cls, "_resolve_provider_class")
    assert not hasattr(cls(), "_resolve_provider_class")


def test_collect_from_loaded_provider() -> None:
    from apiproxy.provider import ApiProxyProvider

    instance = _load_api_proxy_module()()
    instance._log = SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    )
    instance._provider = ApiProxyProvider()
    fake = _FakeProvider()
    state = SimpleNamespace(
        modules=_Loaded({
            "fs": SimpleNamespace(_provider=fake),
            "db": SimpleNamespace(_provider=None),
            "apiproxy": SimpleNamespace(_provider=object()),
        }),
    )
    instance._collect_methods(state)
    assert instance._provider.registry.get_method("fs", "ping") is not None
    assert "db" not in instance._provider.registry.list_modules()
    assert "apiproxy" not in instance._provider.registry.list_modules()
