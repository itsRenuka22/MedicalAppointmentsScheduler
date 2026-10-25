"""Key/value Store interface. MemoryStore for tests, CtxStore over hosted ctx.storage."""
import json
from typing import Any, Optional, Protocol


class Store(Protocol):
    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
    def delete(self, key: str) -> None: ...


class MemoryStore:
    """Values are JSON round-tripped so tests catch anything hosted storage could not hold."""

    def __init__(self):
        self._d: dict[str, str] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return json.loads(self._d[key]) if key in self._d else default

    def set(self, key: str, value: Any) -> None:
        self._d[key] = json.dumps(value)

    def delete(self, key: str) -> None:
        self._d.pop(key, None)


class CtxStore:
    """Adapter over a hosted agent's ctx.storage (persists between messages)."""

    def __init__(self, storage):
        self._s = storage

    def get(self, key: str, default: Any = None) -> Any:
        v = self._s.get(key)
        return default if v is None else v

    def set(self, key: str, value: Any) -> None:
        self._s.set(key, value)

    def delete(self, key: str) -> None:
        try:
            self._s.remove(key)
        except Exception:  # missing key
            pass
