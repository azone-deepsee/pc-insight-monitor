from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List


@dataclass
class MonitorEvent:
    """タイムライン用の統一イベント形式。"""

    timestamp: datetime
    source: str
    category: str
    message: str
    severity: str = "info"

    def to_row(self) -> tuple:
        return (
            self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            self.source,
            self.category,
            self.message,
            self.severity,
        )


@dataclass
class EventBus:
    """監視スレッドとUIの間でイベントを受け渡す。"""

    _listeners: List[Callable[[MonitorEvent], None]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def subscribe(self, listener: Callable[[MonitorEvent], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def publish(self, event: MonitorEvent) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener(event)
