from __future__ import annotations

import json
import subprocess
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

from .base import EventBus, MonitorEvent

POLL_INTERVAL_SEC = 2.0

POWERSHELL = [
    "powershell",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-Command",
    (
        "$ports = Get-PnpDevice -Class Ports -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName, InstanceId, Status; "
        "$usb = Get-PnpDevice -Class USB -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName, InstanceId, Status; "
        "@{ports=$ports; usb=$usb} | ConvertTo-Json -Depth 4 -Compress"
    ),
]


def _decode_powershell_output(data: bytes) -> str:
    """日本語WindowsのPowerShell出力（主にcp932）をデコードする。"""
    if not data:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("cp932", errors="replace")


class UsbWatcher:
    """COMポートとUSBデバイスの状態変化を監視する。"""

    def __init__(self, bus: EventBus, interval: float = POLL_INTERVAL_SEC) -> None:
        self.bus = bus
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._known_ports: Dict[str, str] = {}
        self._known_usb: Dict[str, str] = {}
        self.latest_ports: List[dict] = []
        self.latest_usb: List[dict] = []

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="UsbWatcher", daemon=True)
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
                        source="usb_watcher",
                        category="error",
                        message=f"USB/COM監視エラー: {exc}",
                        severity="error",
                    )
                )
            self._stop.wait(self.interval)

    def _poll(self) -> None:
        raw = self._fetch_devices()
        ports = raw.get("ports") or []
        usb = raw.get("usb") or []

        if isinstance(ports, dict):
            ports = [ports]
        if isinstance(usb, dict):
            usb = [usb]

        self.latest_ports = ports
        self.latest_usb = usb

        self._detect_changes(ports, self._known_ports, "COM", "port")
        self._detect_changes(usb, self._known_usb, "USB", "device")

    def _fetch_devices(self) -> dict:
        result = subprocess.run(
            POWERSHELL,
            capture_output=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            stderr = _decode_powershell_output(result.stderr).strip()
            raise RuntimeError(stderr or "PowerShell failed")
        output = _decode_powershell_output(result.stdout).strip()
        if not output:
            return {"ports": [], "usb": []}
        return json.loads(output)

    def _detect_changes(
        self,
        devices: List[dict],
        known: Dict[str, str],
        label: str,
        category: str,
    ) -> None:
        current: Dict[str, str] = {}
        for item in devices:
            name = (item.get("FriendlyName") or "不明").strip()
            instance_id = (item.get("InstanceId") or name).strip()
            status = (item.get("Status") or "Unknown").strip()
            current[instance_id] = status

            prev = known.get(instance_id)
            if prev is None:
                self.bus.publish(
                    MonitorEvent(
                        timestamp=datetime.now(),
                        source=label,
                        category=category,
                        message=f"{name} を検出 (Status: {status})",
                        severity=self._severity_for_status(status),
                    )
                )
            elif prev != status:
                self.bus.publish(
                    MonitorEvent(
                        timestamp=datetime.now(),
                        source=label,
                        category=category,
                        message=f"{name} が {prev} → {status} に変化",
                        severity=self._severity_for_status(status),
                    )
                )

        for instance_id, prev_status in known.items():
            if instance_id not in current:
                self.bus.publish(
                    MonitorEvent(
                        timestamp=datetime.now(),
                        source=label,
                        category=category,
                        message=f"{instance_id} が一覧から消えました (前回: {prev_status})",
                        severity="warning",
                    )
                )

        known.clear()
        known.update(current)

    @staticmethod
    def _severity_for_status(status: str) -> str:
        normalized = status.lower()
        if normalized == "ok":
            return "info"
        if normalized in {"unknown", "error", "degraded"}:
            return "warning"
        return "info"

    def summary(self) -> dict:
        port_ok = sum(1 for p in self.latest_ports if (p.get("Status") or "").lower() == "ok")
        port_unknown = sum(
            1 for p in self.latest_ports if (p.get("Status") or "").lower() == "unknown"
        )
        usb_ok = sum(1 for u in self.latest_usb if (u.get("Status") or "").lower() == "ok")
        usb_unknown = sum(
            1 for u in self.latest_usb if (u.get("Status") or "").lower() == "unknown"
        )
        return {
            "com_total": len(self.latest_ports),
            "com_ok": port_ok,
            "com_unknown": port_unknown,
            "usb_total": len(self.latest_usb),
            "usb_ok": usb_ok,
            "usb_unknown": usb_unknown,
        }
