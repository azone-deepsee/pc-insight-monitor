from __future__ import annotations

import subprocess
import threading
import time
from datetime import datetime
from typing import Optional

from .base import EventBus, MonitorEvent
from .metrics_store import MetricsStore

POLL_INTERVAL_SEC = 2.0

GPU_PS = [
    "powershell",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    (
        "$g = Get-Counter '\\GPU Engine(*)\\Utilization Percentage' -ErrorAction SilentlyContinue; "
        "if ($g -and $g.CounterSamples) { "
        "  ($g.CounterSamples | Measure-Object -Property CookedValue -Maximum).Maximum "
        "} else { -1 }"
    ),
]


class SystemWatcher:
    """CPU / メモリ / GPU 使用率を監視する。"""

    def __init__(
        self,
        bus: EventBus,
        metrics: MetricsStore,
        interval: float = POLL_INTERVAL_SEC,
        gpu_enabled: bool = True,
    ) -> None:
        self.bus = bus
        self.metrics = metrics
        self.interval = interval
        self.gpu_enabled = gpu_enabled
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._psutil = self._load_psutil()
        self._last_cpu_alert = 0.0
        self._last_mem_alert = 0.0

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
                    source="system",
                    category="warning",
                    message="psutil 未インストールのため CPU/メモリ監視は無効です",
                    severity="warning",
                )
            )
            return
        if self._thread and self._thread.is_alive():
            return
        self._psutil.cpu_percent(interval=None)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="SystemWatcher", daemon=True)
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
                        source="system",
                        category="error",
                        message=f"システム監視エラー: {exc}",
                        severity="error",
                    )
                )
            self._stop.wait(self.interval)

    def _poll(self) -> None:
        now = datetime.now()
        psutil = self._psutil

        cpu = float(psutil.cpu_percent(interval=None))
        mem = float(psutil.virtual_memory().percent)

        self.metrics.add("cpu_percent", cpu, now)
        self.metrics.add("memory_percent", mem, now)

        gpu = self._read_gpu_percent()
        if gpu is not None and gpu >= 0:
            self.metrics.add("gpu_percent", gpu, now)

        self._maybe_alert_cpu(cpu, now)
        self._maybe_alert_mem(mem, now)

    def _read_gpu_percent(self) -> Optional[float]:
        if not self.gpu_enabled:
            return None
        try:
            result = subprocess.run(
                GPU_PS,
                capture_output=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                return None
            text = (result.stdout or b"").decode("utf-8", errors="replace").strip()
            if not text or text == "-1":
                return None
            return float(text)
        except Exception:
            return None

    def _maybe_alert_cpu(self, cpu: float, now: datetime) -> None:
        if cpu < 90:
            return
        if time.monotonic() - self._last_cpu_alert < 30:
            return
        self._last_cpu_alert = time.monotonic()
        self.bus.publish(
            MonitorEvent(
                timestamp=now,
                source="system",
                category="cpu",
                message=f"CPU使用率が高い状態です: {cpu:.0f}%",
                severity="warning",
            )
        )

    def _maybe_alert_mem(self, mem: float, now: datetime) -> None:
        if mem < 90:
            return
        if time.monotonic() - self._last_mem_alert < 30:
            return
        self._last_mem_alert = time.monotonic()
        self.bus.publish(
            MonitorEvent(
                timestamp=now,
                source="system",
                category="memory",
                message=f"メモリ使用率が高い状態です: {mem:.0f}%",
                severity="warning",
            )
        )

    def summary(self) -> dict:
        return {
            "cpu_percent": self.metrics.latest("cpu_percent"),
            "memory_percent": self.metrics.latest("memory_percent"),
            "gpu_percent": self.metrics.latest("gpu_percent"),
        }
