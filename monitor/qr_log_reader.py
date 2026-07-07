from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from .base import MonitorEvent

CONNECT_WORDS = ("connect", "connected", "接続", "接続され", "attach", "enumerated")
DISCONNECT_WORDS = ("disconnect", "disconnected", "切断", "遮断", "remove", "removed", "detach")

DATE_PATTERNS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y/%m/%d %H:%M:%S.%f",
)


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="cp932", errors="replace")


def _parse_timestamp(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in DATE_PATTERNS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    # 行全体から日時を探す
    match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)", value)
    if not match:
        return None
    raw = match.group(1).replace("/", "-").replace("T", " ")
    for fmt in DATE_PATTERNS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _classify_message(message: str) -> str:
    lower = message.lower()
    if any(word in lower or word in message for word in CONNECT_WORDS):
        return "connect"
    if any(word in lower or word in message for word in DISCONNECT_WORDS):
        return "disconnect"
    return "status"


def _rows_from_csv(path: Path) -> Iterable[MonitorEvent]:
    text = _read_text(path)
    if not text.strip():
        return []

    reader = csv.reader(text.splitlines())
    rows = list(reader)
    if not rows:
        return []

    header = [cell.strip().lower() for cell in rows[0]]
    has_header = any(key in header for key in ("time", "timestamp", "日時", "時刻", "datetime"))

    events: List[MonitorEvent] = []
    data_rows = rows[1:] if has_header else rows

    time_idx = _find_column(header, ("time", "timestamp", "日時", "時刻", "datetime")) if has_header else None
    message_idx = _find_column(
        header, ("message", "event", "action", "内容", "状態", "種別", "type", "log")
    ) if has_header else None

    for row in data_rows:
        if not row or all(not cell.strip() for cell in row):
            continue

        if time_idx is not None and time_idx < len(row):
            timestamp = _parse_timestamp(row[time_idx])
            message = row[message_idx] if message_idx is not None and message_idx < len(row) else " ".join(row)
        else:
            joined = ",".join(row)
            timestamp = _parse_timestamp(joined)
            message = joined

        if timestamp is None:
            continue

        category = _classify_message(message)
        severity = "warning" if category == "disconnect" else "info"
        events.append(
            MonitorEvent(
                timestamp=timestamp,
                source="QRログ",
                category=category,
                message=f"{path.name}: {message}",
                severity=severity,
            )
        )
    return events


def _find_column(header: List[str], candidates: tuple[str, ...]) -> int | None:
    for idx, name in enumerate(header):
        if name in candidates:
            return idx
    return None


def load_qr_log_events(directory: str, pattern: str = "*.csv") -> List[MonitorEvent]:
    base = Path(directory)
    if not directory or not base.is_dir():
        return []

    events: List[MonitorEvent] = []
    for path in sorted(base.glob(pattern)):
        if not path.is_file():
            continue
        try:
            events.extend(_rows_from_csv(path))
        except OSError:
            continue
    events.sort(key=lambda item: item.timestamp)
    return events
