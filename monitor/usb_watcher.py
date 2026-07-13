from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

from .base import EventBus, MonitorEvent

POLL_INTERVAL_SEC = 3.0


def _fetch_devices_wmi() -> dict:
    """WMI で COM/USB デバイス一覧を取得（PowerShell 起動不要）。"""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        wmi = win32com.client.GetObject("winmgmts:")
        ports: List[dict] = []
        usb: List[dict] = []

        for item in wmi.ExecQuery(
            "SELECT Caption, DeviceID, Status FROM Win32_PnPEntity WHERE PNPClass='Ports'"
        ):
            ports.append(
                {
                    "FriendlyName": str(item.Caption or "不明"),
                    "InstanceId": str(item.DeviceID or ""),
                    "Status": str(item.Status or "Unknown"),
                }
            )

        for item in wmi.ExecQuery(
            "SELECT Caption, DeviceID, Status FROM Win32_PnPEntity WHERE PNPClass='USB'"
        ):
            usb.append(
                {
                    "FriendlyName": str(item.Caption or "不明"),
                    "InstanceId": str(item.DeviceID or ""),
                    "Status": str(item.Status or "Unknown"),
                }
            )

        return {"ports": ports, "usb": usb}
    finally:
        pythoncom.CoUninitialize()


class UsbWatcher:
    """COMポートとUSBデバイスの状態変化を監視する。"""

    def __init__(
        self,
        bus: EventBus,
        interval: float = POLL_INTERVAL_SEC,
        suppress_initial_events: bool = True,
    ) -> None:
        self.bus = bus
        self.interval = interval
        self.suppress_initial_events = suppress_initial_events
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._known_ports: Dict[str, str] = {}
        self._known_usb: Dict[str, str] = {}
        self._baselined = False
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
        raw = _fetch_devices_wmi()
        ports = raw.get("ports") or []
        usb = raw.get("usb") or []

        publish_events = not (self.suppress_initial_events and not self._baselined)

        self.latest_ports = ports
        self.latest_usb = usb

        self._detect_changes(ports, self._known_ports, "COM", "port", publish_events)
        self._detect_changes(usb, self._known_usb, "USB", "device", publish_events)

        if not self._baselined:
            self._baselined = True

    def _detect_changes(
        self,
        devices: List[dict],
        known: Dict[str, str],
        label: str,
        category: str,
        publish_events: bool,
    ) -> None:
        current: Dict[str, str] = {}
        for item in devices:
            name = (item.get("FriendlyName") or "不明").strip()
            instance_id = (item.get("InstanceId") or name).strip()
            status = (item.get("Status") or "Unknown").strip()
            current[instance_id] = status

            prev = known.get(instance_id)
            if not publish_events:
                continue
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

        if publish_events:
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
