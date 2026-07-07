from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path

from .base import MonitorEvent


class CsvLogger:
  """ログをローカルフォルダへ保存（ファイルサーバへの常時書き込みを避ける）。"""

  HEADERS = ("timestamp", "source", "category", "message", "severity")

  def __init__(self, log_dir: Path | None = None) -> None:
      base = log_dir or Path(os.environ.get("LOCALAPPDATA", ".")) / "PCInsightMonitor" / "logs"
      base.mkdir(parents=True, exist_ok=True)
      self.log_dir = base
      stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
      self.file_path = base / f"session_{stamp}.csv"
      self._write_header()

  def _write_header(self) -> None:
      with self.file_path.open("w", newline="", encoding="utf-8-sig") as fp:
          writer = csv.writer(fp)
          writer.writerow(self.HEADERS)

  def write(self, event: MonitorEvent) -> None:
      with self.file_path.open("a", newline="", encoding="utf-8-sig") as fp:
          writer = csv.writer(fp)
          writer.writerow(event.to_row())

  @property
  def display_path(self) -> str:
      return str(self.file_path)
