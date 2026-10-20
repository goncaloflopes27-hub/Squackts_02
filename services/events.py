from __future__ import annotations

import logging
from collections.abc import Callable
from threading import RLock

ChangeListener = Callable[[str], None]


class ChangeEvents:
    """Publish committed changes without coupling domain services to Qt."""

    def __init__(self) -> None:
        self._listeners: list[ChangeListener] = []
        self._lock = RLock()

    def subscribe(self, listener: ChangeListener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def emit(self, topic: str) -> None:
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(topic)
            except Exception:
                logging.getLogger(__name__).exception("Failed to refresh %s", topic)

    publish = emit
