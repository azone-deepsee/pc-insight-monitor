from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, Dict, List, Optional, Tuple


@dataclass
class MetricSample:
    timestamp: datetime
    value: float


@dataclass
class MetricsStore:
    """グラフ表示用の時系列メトリクス（リングバッファ）。"""

    max_points: int = 300
    _series: Dict[str, Deque[MetricSample]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, name: str, value: float, timestamp: datetime | None = None) -> None:
        ts = timestamp or datetime.now()
        with self._lock:
            if name not in self._series:
                self._series[name] = deque(maxlen=self.max_points)
            self._series[name].append(MetricSample(ts, value))

    def get_series(self, name: str) -> List[Tuple[datetime, float]]:
        with self._lock:
            items = list(self._series.get(name, ()))
        return [(s.timestamp, s.value) for s in items]

    def names(self) -> List[str]:
        with self._lock:
            return list(self._series.keys())

    def latest(self, name: str) -> Optional[float]:
        with self._lock:
            series = self._series.get(name)
            if not series:
                return None
            return series[-1].value

    def clear(self) -> None:
        with self._lock:
            self._series.clear()
