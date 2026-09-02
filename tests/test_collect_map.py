"""Tests for ApiProxyModule._resolve_provider_class mapping."""
from __future__ import annotations

import importlib.util
from pathlib import Path


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


def test_resolve_provider_map_keys() -> None:
    instance = _load_api_proxy_module()()
    resolved = {
        name: instance._resolve_provider_class(name)
        for name in ("auth", "llm", "workspace", "system", "fs", "notification", "db")
    }
    keys = {name for name, cls in resolved.items() if cls is not None}
    assert "auth" in keys
    assert "llm" in keys
    assert resolved["db"] is None
    if resolved["workspace"] is not None:
        assert resolved["workspace"].__name__ == "WorkspaceProvider"
    if resolved["system"] is not None:
        assert resolved["system"].__name__ == "SystemProvider"
    if resolved["fs"] is not None:
        assert resolved["fs"].__name__ == "FsProvider"
    if resolved["notification"] is not None:
        assert resolved["notification"].__name__ == "NotificationProvider"
    assert keys <= {"auth", "llm", "workspace", "system", "fs", "notification"}
