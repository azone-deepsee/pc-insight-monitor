from __future__ import annotations

import re
import subprocess
import threading
import time
from datetime import datetime
from typing import Dict, Optional

from .base import EventBus, MonitorEvent
from .metrics_store import MetricsStore

POLL_INTERVAL_SEC = 3.0
PING_INTERVAL_SEC = 5.0


class NetworkWatcher:
    """ネットワーク I/O と疎通（ping）を監視する。"""

    def __init__(
        self,
        bus: EventBus,
        metrics: MetricsStore,
        ping_target: str = "8.8.8.8",
        interval: float = POLL_INTERVAL_SEC,
        ping_interval: float = PING_INTERVAL_SEC,
    ) -> None:
        self.bus = bus
        self.metrics = metrics
        self.ping_target = ping_target.strip() or "8.8.8.8"
        self.interval = interval
        self.ping_interval = ping_interval
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._psutil = self._load_psutil()
        self._last_io: Optional[Dict[str, int]] = None
        self._last_ping_at = 0.0
        self._last_ping_alert = 0.0

    @staticmethod
    def _load_psutil():
        try:
            import psutil

            return psutil
        except ImportError:
            return None

    def start(self) -> None:
        if not self._psutil:
            self.bus.publish(
                MonitorEvent(
                    timestamp=datetime.now(),
                    source="network",
                    category="warning",
                    message="psutil 未インストールのためネットワーク監視は無効です",
                    severity="warning",
                )
            )
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="NetworkWatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._poll()
            except Exception as exc:
                self.bus.publish(
                    MonitorEvent(
                        timestamp=datetime.now(),
                        source="network",
                        category="error",
                        message=f"ネットワーク監視エラー: {exc}",
                        severity="error",
                    )
                )
            self._stop.wait(self.interval)

    def _poll(self) -> None:
        now = datetime.now()
        psutil = self._psutil

        counters = psutil.net_io_counters()
        current = {"bytes_sent": counters.bytes_sent, "bytes_recv": counters.bytes_recv}
        if self._last_io is not None:
            elapsed = max(self.interval, 0.1)
            sent_kbps = (current["bytes_sent"] - self._last_io["bytes_sent"]) * 8 / 1024 / elapsed
            recv_kbps = (current["bytes_recv"] - self._last_io["bytes_recv"]) * 8 / 1024 / elapsed
            self.metrics.add("net_sent_kbps", max(0.0, sent_kbps), now)
            self.metrics.add("net_recv_kbps", max(0.0, recv_kbps), now)
        self._last_io = current

        if time.monotonic() - self._last_ping_at >= self.ping_interval:
            self._last_ping_at = time.monotonic()
            ping_ms = self._ping()
            if ping_ms is not None:
                self.metrics.add("ping_ms", ping_ms, now)
                if ping_ms < 0:
                    self._maybe_alert_ping_fail(now)

    def _ping(self) -> Optional[float]:
        try:
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "1000", self.ping_target],
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                return -1.0
            text = (result.stdout or b"").decode("cp932", errors="replace")
            match = re.search(r"(?:時間|time)[=<]\s*(\d+)\s*ms", text, re.IGNORECASE)
            if not match:
                return -1.0
            return float(match.group(1))
        except Exception:
            return -1.0

    def _maybe_alert_ping_fail(self, now: datetime) -> None:
        if time.monotonic() - self._last_ping_alert < 30:
            return
        self._last_ping_alert = time.monotonic()
        self.bus.publish(
            MonitorEvent(
                timestamp=now,
                source="network",
                category="ping",
                message=f"疎通確認失敗: {self.ping_target} に応答がありません",
                severity="warning",
            )
        )

    def summary(self) -> dict:
        return {
            "ping_ms": self.metrics.latest("ping_ms"),
            "net_sent_kbps": self.metrics.latest("net_sent_kbps"),
            "net_recv_kbps": self.metrics.latest("net_recv_kbps"),
        }
