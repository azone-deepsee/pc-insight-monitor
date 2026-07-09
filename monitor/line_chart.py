from __future__ import annotations

import tkinter as tk
from datetime import datetime
from typing import List, Tuple


class LineChart(tk.Canvas):
    """依存追加なしの簡易折れ線グラフ。"""

    PADDING = 36

    def __init__(
        self,
        master: tk.Misc,
        title: str,
        unit: str = "",
        height: int = 160,
        line_color: str = "#2563eb",
        warn_above: float | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, height=height, background="#1e1e2e", highlightthickness=0, **kwargs)
        self.title = title
        self.unit = unit
        self.line_color = line_color
        self.warn_above = warn_above
        self._data: List[Tuple[datetime, float]] = []
        self.bind("<Configure>", lambda _e: self._redraw())

    def set_data(self, data: List[Tuple[datetime, float]]) -> None:
        self._data = [(ts, val) for ts, val in data if val is not None and val >= 0]
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        w = max(self.winfo_width(), 10)
        h = max(self.winfo_height(), 10)
        pad = self.PADDING

        self.create_rectangle(0, 0, w, h, fill="#1e1e2e", outline="")
        self.create_text(pad, 12, text=self.title, anchor=tk.W, fill="#cdd6f4", font=("Segoe UI", 9, "bold"))

        if len(self._data) < 2:
            self.create_text(
                w // 2,
                h // 2,
                text="データ収集中...",
                fill="#6c7086",
                font=("Segoe UI", 10),
            )
            return

        values = [v for _, v in self._data]
        ymin = min(values)
        ymax = max(values)
        if ymax - ymin < 1e-6:
            ymax = ymin + 1.0
        margin = (ymax - ymin) * 0.1
        ymin -= margin
        ymax += margin

        chart_w = w - pad * 2
        chart_h = h - pad * 1.6
        x0, y0 = pad, pad + 8
        x1, y1 = x0 + chart_w, y0 + chart_h

        self.create_line(x0, y1, x1, y1, fill="#45475a")
        self.create_line(x0, y0, x0, y1, fill="#45475a")

        if self.warn_above is not None and ymin <= self.warn_above <= ymax:
            wy = y1 - (self.warn_above - ymin) / (ymax - ymin) * chart_h
            self.create_line(x0, wy, x1, wy, fill="#f38ba8", dash=(4, 4))

        points: list[float] = []
        n = len(self._data)
        for i, (_, val) in enumerate(self._data):
            x = x0 + (i / (n - 1)) * chart_w
            y = y1 - (val - ymin) / (ymax - ymin) * chart_h
            points.extend([x, y])

        self.create_line(*points, fill=self.line_color, width=2, smooth=True)

        latest = values[-1]
        unit = f" {self.unit}" if self.unit else ""
        self.create_text(
            x1,
            12,
            text=f"{latest:.1f}{unit}",
            anchor=tk.E,
            fill="#a6e3a1",
            font=("Segoe UI", 10, "bold"),
        )
        self.create_text(x0 - 4, y1, text=f"{ymin:.0f}", anchor=tk.E, fill="#6c7086", font=("Segoe UI", 8))
        self.create_text(x0 - 4, y0, text=f"{ymax:.0f}", anchor=tk.E, fill="#6c7086", font=("Segoe UI", 8))
