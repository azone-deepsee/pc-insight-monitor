"""
PC Insight Monitor - たたき台

サーバ不要。ファイルサーバ上のフォルダから run.bat を実行し、
各PC上でローカル監視＋デスクトップUIとして動作する。
"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import messagebox, ttk

from monitor import CsvLogger, EventBus, EventWatcher, MonitorEvent, UsbWatcher, load_config, load_qr_log_events


class App(tk.Tk):
    POLL_UI_MS = 500
    MAX_TIMELINE_ROWS = 500

    def __init__(self) -> None:
        super().__init__()
        self.title("PC Insight Monitor α v1.0")
        self.geometry("1100x720")
        self.minsize(900, 600)

        self.bus = EventBus()
        self.logger = CsvLogger()
        self.config = load_config()
        self.usb_watcher = UsbWatcher(self.bus)
        self.event_watcher = EventWatcher(self.bus)

        self._event_queue: queue.Queue[MonitorEvent] = queue.Queue()
        self._monitoring = False

        self.bus.subscribe(self._on_monitor_event)

        self._build_ui()
        self._schedule_ui_refresh()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=8)
        header.pack(fill=tk.X)

        self.stat_vars = {
            "com_total": tk.StringVar(value="-"),
            "com_ok": tk.StringVar(value="-"),
            "com_unknown": tk.StringVar(value="-"),
            "usb_total": tk.StringVar(value="-"),
            "event_count": tk.StringVar(value="0"),
            "status": tk.StringVar(value="停止中"),
        }

        stats = [
            ("COM総数", "com_total"),
            ("COM正常", "com_ok"),
            ("COM Unknown", "com_unknown"),
            ("USB総数", "usb_total"),
            ("タイムライン", "event_count"),
            ("状態", "status"),
        ]
        for idx, (label, key) in enumerate(stats):
            frame = ttk.LabelFrame(header, text=label, padding=6)
            frame.grid(row=0, column=idx, padx=4, sticky="nsew")
            ttk.Label(frame, textvariable=self.stat_vars[key], font=("Segoe UI", 12, "bold")).pack()

        controls = ttk.Frame(self, padding=(8, 0, 8, 8))
        controls.pack(fill=tk.X)
        ttk.Button(controls, text="監視開始", command=self.start_monitoring).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="監視停止", command=self.stop_monitoring).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="一覧を更新", command=self.refresh_device_tables).pack(side=tk.LEFT, padx=4)
        ttk.Button(controls, text="QRログ取込", command=self.import_qr_logs).pack(side=tk.LEFT, padx=4)
        ttk.Label(
            controls,
            text=f"ログ保存先: {self.logger.display_path}",
        ).pack(side=tk.RIGHT, padx=4)

        notebook = ttk.Notebook(self, padding=8)
        notebook.pack(fill=tk.BOTH, expand=True)

        self.overview_text = tk.Text(notebook, height=10, wrap=tk.WORD, state=tk.DISABLED)
        com_frame, self.com_tree = self._make_tree(notebook, ("名前", "Status", "InstanceId"))
        usb_frame, self.usb_tree = self._make_tree(notebook, ("名前", "Status", "InstanceId"))
        timeline_frame, self.timeline_tree = self._make_tree(
            notebook, ("時刻", "ソース", "カテゴリ", "内容", "重要度")
        )
        event_frame, self.event_tree = self._make_tree(notebook, ("時刻", "ソース", "EventID", "内容"))

        notebook.add(self.overview_text, text="概要")
        notebook.add(com_frame, text="COM一覧")
        notebook.add(usb_frame, text="USB一覧")
        notebook.add(timeline_frame, text="タイムライン")
        notebook.add(event_frame, text="イベントログ")

        self._write_overview()

    def _make_tree(
        self, parent: ttk.Notebook, columns: tuple[str, ...]
    ) -> tuple[ttk.Frame, ttk.Treeview]:
        frame = ttk.Frame(parent)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=18)
        for col in columns:
            tree.heading(col, text=col)
            width = 420 if col in ("内容", "InstanceId") else 120
            tree.column(col, width=width, anchor=tk.W)
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        return frame, tree

    def _write_overview(self) -> None:
        qr_cfg = self.config.get("qr_log", {})
        qr_dir = qr_cfg.get("directory") or "（未設定）"
        lines = [
            "PC Insight Monitor - たたき台（ポータブル Python 配布向け）",
            "",
            "配布の流れ:",
            "  1. 開発PCで setup_portable.bat を1回実行",
            "  2. pc_insight_monitor フォルダ一式をファイルサーバへ配置",
            "  3. 現場PCでは run.bat を実行（Pythonのインストール不要）",
            "",
            "この版でできること:",
            "  - COMポート / USBデバイスの状態監視",
            "  - Windowsイベントログ（System）のUSB関連イベント監視",
            "  - 変化を1本のタイムラインへ表示",
            "  - QRツールのUSB接続CSVをタイムラインへ取込（config.json）",
            "  - CSVログをローカル（%LOCALAPPDATA%\\PCInsightMonitor\\logs）へ保存",
            "",
            "運用方針（現時点）:",
            "  - 調査時に手動起動するツール（常時バックグラウンド監視は将来対応）",
            "  - QRツールのexe差し替えは不要",
            "",
            f"QRログフォルダ設定: {qr_dir}",
            "",
            "使い方:",
            "  1. run.bat をダブルクリック",
            "  2. 「監視開始」を押す",
            "  3. 必要なら「QRログ取込」で既存CSVを統合",
            "  4. USB抜き差しやCOM異常を発生させ、タイムラインを確認",
        ]
        self.overview_text.configure(state=tk.NORMAL)
        self.overview_text.delete("1.0", tk.END)
        self.overview_text.insert(tk.END, "\n".join(lines))
        self.overview_text.configure(state=tk.DISABLED)

    def _on_monitor_event(self, event: MonitorEvent) -> None:
        self._event_queue.put(event)
        try:
            self.logger.write(event)
        except Exception:
            pass

    def import_qr_logs(self) -> None:
        qr_cfg = self.config.get("qr_log", {})
        directory = (qr_cfg.get("directory") or "").strip()
        pattern = qr_cfg.get("pattern") or "*.csv"
        if not directory:
            messagebox.showinfo(
                "QRログ取込",
                "config.json の qr_log.directory にQRツールのログフォルダを設定してください。",
            )
            return

        events = load_qr_log_events(directory, pattern)
        if not events:
            messagebox.showwarning("QRログ取込", f"読み込めるログがありません:\n{directory}")
            return

        for event in events:
            self._event_queue.put(event)
            try:
                self.logger.write(event)
            except Exception:
                pass

        messagebox.showinfo("QRログ取込", f"{len(events)} 件をタイムラインへ取り込みました。")

    def start_monitoring(self) -> None:
        if self._monitoring:
            return
        self.usb_watcher.start()
        self.event_watcher.start()
        self._monitoring = True
        self.stat_vars["status"].set("監視中")
        self.refresh_device_tables()

    def stop_monitoring(self) -> None:
        self.usb_watcher.stop()
        self.event_watcher.stop()
        self._monitoring = False
        self.stat_vars["status"].set("停止中")

    def refresh_device_tables(self) -> None:
        if not self._monitoring:
            try:
                self.usb_watcher._poll()
            except Exception as exc:
                messagebox.showerror("更新エラー", str(exc))
                return

        self._fill_tree(self.com_tree, self.usb_watcher.latest_ports)
        self._fill_tree(self.usb_tree, self.usb_watcher.latest_usb)
        self._fill_event_tree()
        self._update_summary()

    @staticmethod
    def _fill_tree(tree: ttk.Treeview, items: list[dict]) -> None:
        tree.delete(*tree.get_children())
        for item in items:
            tree.insert(
                "",
                tk.END,
                values=(
                    item.get("FriendlyName", ""),
                    item.get("Status", ""),
                    item.get("InstanceId", ""),
                ),
            )

    def _fill_event_tree(self) -> None:
        self.event_tree.delete(*self.event_tree.get_children())
        for item in self.event_watcher.recent_events[:100]:
            ts = item["time"].strftime("%Y-%m-%d %H:%M:%S")
            self.event_tree.insert(
                "",
                tk.END,
                values=(ts, item.get("source", ""), item.get("event_id", ""), item.get("message", "")),
            )

    def _update_summary(self) -> None:
        summary = self.usb_watcher.summary()
        self.stat_vars["com_total"].set(str(summary["com_total"]))
        self.stat_vars["com_ok"].set(str(summary["com_ok"]))
        self.stat_vars["com_unknown"].set(str(summary["com_unknown"]))
        self.stat_vars["usb_total"].set(str(summary["usb_total"]))

        if summary["com_unknown"] > 0:
            self.stat_vars["com_unknown"].set(f"{summary['com_unknown']} ⚠")

    def _schedule_ui_refresh(self) -> None:
        self._drain_event_queue()
        if self._monitoring:
            self.refresh_device_tables()
        self.after(self.POLL_UI_MS, self._schedule_ui_refresh)

    def _drain_event_queue(self) -> None:
        count = int(self.stat_vars["event_count"].get() or 0)
        while True:
            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                break
            count += 1
            self.timeline_tree.insert("", 0, values=event.to_row())
            children = self.timeline_tree.get_children()
            if len(children) > self.MAX_TIMELINE_ROWS:
                for item in children[self.MAX_TIMELINE_ROWS :]:
                    self.timeline_tree.delete(item)
        self.stat_vars["event_count"].set(str(count))

    def _on_close(self) -> None:
        self.stop_monitoring()
        self.destroy()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
