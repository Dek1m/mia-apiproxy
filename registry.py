"""MethodRegistry — реестр API-методов модулей.

Собирает метаданные из функций с @auth_method (_auth_method_meta).
Хранит MethodMeta для каждого метода.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = ["MethodRegistry", "MethodMeta"]


@dataclass
class MethodMeta:
    """Метаданные одного API-метода."""

    name: str
    description: str
    args: dict[str, str]
    return_type: str | None
    public: bool
    required_permission: str | None
    func: Callable[..., Any] = field(repr=False)
    module: str = ""


class MethodRegistry:
    """Реестр API-методов.

    Поддерживает:
    - Регистрацию из функций с _auth_method_meta
    - Поиск по module_name + method_name
    - Список модулей и методов
    """

    def __init__(self, log: Any | None = None) -> None:
        self._methods: dict[str, dict[str, MethodMeta]] = {}
        self._log = log

    def register(
        self,
        module_name: str,
        method_name: str,
        metadata: dict[str, Any],
        func: Callable[..., Any],
    ) -> None:
        """Зарегистрировать метод в реестре.

        Args:
            module_name: Имя модуля (auth, workspace, ...).
            method_name: Имя метода.
            metadata: Метаданные из _auth_method_meta.
            func: Оригинальная функция.

        Raises:
            ValueError: Если метод с таким именем уже зарегистрирован в модуле.
        """
        if module_name not in self._methods:
            self._methods[module_name] = {}

        if method_name in self._methods[module_name]:
            raise ValueError(
                f"Duplicate method '{method_name}' in module '{module_name}'"
            )

        meta = MethodMeta(
            name=metadata.get("name", method_name),
            description=metadata.get("description", ""),
            args=metadata.get("args", {}),
            return_type=metadata.get("return_type"),
            public=metadata.get("public", False),
            required_permission=metadata.get("required_permission"),
            func=func,
            module=module_name,
        )
        self._methods[module_name][method_name] = meta

    def collect_from_module(
        self,
        provider: Any,
        module_name: str,
    ) -> int:
        """Собрать методы из экземпляра провайдера/класса.

        Проходит по атрибутам, ищет функции с _auth_method_meta.

        Args:
            provider: Экземпляр провайдера (AuthProvider, LLMProvider, ...).
            module_name: Имя модуля.

        Returns:
            Количество зарегистрированных методов.
        """
        count = 0
        for attr_name in dir(provider):
            if attr_name.startswith("_"):
                continue
            attr = getattr(provider, attr_name, None)
            if attr is None:
                continue

            # Обычная функция
            if callable(attr):
                meta = getattr(attr, "_auth_method_meta", None)
                if meta is not None:
                    method_name = meta.get("name", attr_name)
                    try:
                        self.register(module_name, method_name, meta, attr)
                        count += 1
                    except ValueError as e:
                        if self._log is not None:
                            self._log.warning("skip_duplicate_method", error=str(e))
                continue

            # Свойство — проверяем getter
            if isinstance(attr, property) and attr.fget is not None:
                meta = getattr(attr.fget, "_auth_method_meta", None)
                if meta is not None:
                    method_name = meta.get("name", attr_name)
                    try:
                        self.register(module_name, method_name, meta, attr.fget)
                        count += 1
                    except ValueError as e:
                        if self._log is not None:
                            self._log.warning("skip_duplicate_method", error=str(e))

        return count

    def get_method(
        self, module_name: str, method_name: str,
    ) -> MethodMeta | None:
        """Получить метаданные метода."""
        return self._methods.get(module_name, {}).get(method_name)

    def list_modules(self) -> list[str]:
        """Список зарегистрированных модулей."""
        return sorted(self._methods.keys())

    def list_methods(self, module_name: str) -> list[MethodMeta]:
        """Список методов модуля."""
        return list(self._methods.get(module_name, {}).values())

    def list_all_methods(self) -> list[MethodMeta]:
        """Список всех методов всех модулей."""
        result = []
        for module_methods in self._methods.values():
            result.extend(module_methods.values())
        return result

    def has_module(self, module_name: str) -> bool:
        """Проверить, есть ли модуль в реестре."""
        return module_name in self._methods

    def clear(self) -> None:
        """Очистить реестр."""
        self._methods.clear()
