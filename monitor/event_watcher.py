from __future__ import annotations

import threading
from datetime import datetime
from typing import List, Optional

from .base import EventBus, MonitorEvent

POLL_INTERVAL_SEC = 2.0

# USB/COM関連と思われるイベントソース（部分一致）
TARGET_SOURCES = (
    "Kernel-PnP",
    "Kernel-USB",
    "USB",
    "USBHUB",
    "USBXHCI",
    "PnP",
)


class EventWatcher:
    """Windowsイベントログ（System）からUSB関連イベントを監視する。"""

    def __init__(self, bus: EventBus, interval: float = POLL_INTERVAL_SEC) -> None:
        self.bus = bus
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_record = 0
        self.recent_events: List[dict] = []
        self._max_recent = 200
        self._available = self._check_available()

    @staticmethod
    def _check_available() -> bool:
        try:
            import win32evtlog  # noqa: F401

            return True
        except ImportError:
            return False

    def start(self) -> None:
        if not self._available:
            self.bus.publish(
                MonitorEvent(
                    timestamp=datetime.now(),
                    source="eventlog",
                    category="warning",
                    message="pywin32 未インストールのためイベントログ監視は無効です",
                    severity="warning",
                )
            )
            return
        if self._thread and self._thread.is_alive():
            return
        self._initialize_position()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="EventWatcher", daemon=True)
        self._thread.start()

    def _initialize_position(self) -> None:
        """起動時点以降のイベントだけを拾う。"""
        import win32evtlog

        handle = win32evtlog.OpenEventLog(None, "System")
        try:
            flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
            events = win32evtlog.ReadEventLog(handle, flags, 0)
            if events:
                self._last_record = events[0].RecordNumber
        finally:
            win32evtlog.CloseEventLog(handle)

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        import win32evtlog
        import win32evtlogutil

        while not self._stop.is_set():
            try:
                handle = win32evtlog.OpenEventLog(None, "System")
                flags = win32evtlog.EVENTLOG_FORWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
                while True:
                    events = win32evtlog.ReadEventLog(handle, flags, 0)
                    if not events:
                        break
                    for event in events:
                        if event.RecordNumber <= self._last_record:
                            continue
                        self._last_record = event.RecordNumber
                        source = event.SourceName or ""
                        if not self._is_target_source(source):
                            continue
                        try:
                            message = win32evtlogutil.SafeFormatMessage(event, "System")
                        except Exception:
                            message = f"EventID {event.EventID}"
                        message = (message or "").strip().replace("\r\n", " ").replace("\n", " ")
                        if len(message) > 300:
                            message = message[:297] + "..."

                        item = {
                            "time": event.TimeGenerated,
                            "source": source,
                            "event_id": event.EventID,
                            "message": message,
                        }
                        self.recent_events.insert(0, item)
                        self.recent_events = self.recent_events[: self._max_recent]

                        self.bus.publish(
                            MonitorEvent(
                                timestamp=event.TimeGenerated,
                                source="EventLog",
                                category=source,
                                message=f"[{event.EventID}] {message}",
                                severity="warning" if event.EventType in (1, 2) else "info",
                            )
                        )
                win32evtlog.CloseEventLog(handle)
            except Exception as exc:
                self.bus.publish(
                    MonitorEvent(
                        timestamp=datetime.now(),
                        source="eventlog",
                        category="error",
                        message=f"イベントログ監視エラー: {exc}",
                        severity="error",
                    )
                )
            self._stop.wait(self.interval)

    @staticmethod
    def _is_target_source(source: str) -> bool:
        upper = source.upper()
        return any(key.upper() in upper for key in TARGET_SOURCES)
