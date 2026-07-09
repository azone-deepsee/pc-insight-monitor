"""
PC Insight Monitor - たたき台

サーバ不要。ファイルサーバ上のフォルダから run.bat を実行し、
各PC上でローカル監視＋デスクトップUIとして動作する。
"""

from __future__ import annotations

import queue
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from monitor import (
    CsvLogger,
    EventBus,
    EventWatcher,
    LineChart,
    MetricsStore,
    MonitorEvent,
    NetworkWatcher,
    SystemWatcher,
    UsbWatcher,
    load_config,
    load_qr_log_events,
)

SEVERITY_TAGS = {
    "info": {"foreground": "#1e1e1e"},
    "warning": {"foreground": "#b45309", "background": "#fff7ed"},
    "error": {"foreground": "#b91c1c", "background": "#fef2f2"},
}


class App(tk.Tk):
    POLL_UI_MS = 500
    MAX_TIMELINE_ROWS = 500
    CORRELATION_WINDOW_SEC = 10

    def __init__(self) -> None:
        super().__init__()
        self.title("PC Insight Monitor α v1.1")
        self.geometry("1200x780")
        self.minsize(960, 640)

        self.config_data = load_config()
        mon_cfg = self.config_data.get("monitoring", {})
        self.poll_interval = float(mon_cfg.get("poll_interval_sec", 2))

        self.bus = EventBus()
        self.logger = CsvLogger()
        self.metrics = MetricsStore(max_points=int(mon_cfg.get("metrics_max_points", 300)))

        self.usb_watcher = UsbWatcher(self.bus, interval=self.poll_interval)
        self.event_watcher = EventWatcher(self.bus, interval=self.poll_interval)
        self.system_watcher = SystemWatcher(
            self.bus,
            self.metrics,
            interval=self.poll_interval,
            gpu_enabled=bool(mon_cfg.get("enable_gpu", True)),
        )
        self.network_watcher = NetworkWatcher(
            self.bus,
            self.metrics,
            ping_target=str(mon_cfg.get("ping_target", "8.8.8.8")),
            interval=self.poll_interval,
        )

        self._event_queue: queue.Queue[MonitorEvent] = queue.Queue()
        self._all_events: list[MonitorEvent] = []
        self._monitoring = False
        self._timeline_filter = tk.StringVar(value="すべて")

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
            "cpu": tk.StringVar(value="-"),
            "memory": tk.StringVar(value="-"),
            "ping": tk.StringVar(value="-"),
            "event_count": tk.StringVar(value="0"),
            "status": tk.StringVar(value="停止中"),
        }

        stats = [
            ("COM総数", "com_total"),
            ("COM正常", "com_ok"),
            ("COM Unknown", "com_unknown"),
            ("USB総数", "usb_total"),
            ("CPU", "cpu"),
            ("メモリ", "memory"),
            ("Ping", "ping"),
            ("タイムライン", "event_count"),
            ("状態", "status"),
        ]
        for idx, (label, key) in enumerate(stats):
            frame = ttk.LabelFrame(header, text=label, padding=6)
            frame.grid(row=0, column=idx, padx=3, sticky="nsew")
            ttk.Label(frame, textvariable=self.stat_vars[key], font=("Segoe UI", 11, "bold")).pack()

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

        timeline_outer = ttk.Frame(notebook)
        filter_row = ttk.Frame(timeline_outer, padding=(0, 0, 0, 6))
        filter_row.pack(fill=tk.X)
        ttk.Label(filter_row, text="ソース絞込:").pack(side=tk.LEFT, padx=(0, 6))
        filter_combo = ttk.Combobox(
            filter_row,
            textvariable=self._timeline_filter,
            values=["すべて", "COM", "USB", "EventLog", "QRログ", "system", "network"],
            state="readonly",
            width=14,
        )
        filter_combo.pack(side=tk.LEFT)
        filter_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_timeline_filter())
        ttk.Button(filter_row, text="相関ハイライト", command=self._highlight_correlations).pack(
            side=tk.LEFT, padx=8
        )

        timeline_frame, self.timeline_tree = self._make_tree(
            timeline_outer, ("時刻", "ソース", "カテゴリ", "内容", "重要度")
        )
        timeline_frame.pack(fill=tk.BOTH, expand=True)
        for tag, opts in SEVERITY_TAGS.items():
            self.timeline_tree.tag_configure(tag, **opts)

        event_frame, self.event_tree = self._make_tree(notebook, ("時刻", "ソース", "EventID", "内容"))
        charts_frame = self._build_charts_tab(notebook)
        correlation_frame = self._build_correlation_tab(notebook)

        notebook.add(self.overview_text, text="概要")
        notebook.add(com_frame, text="COM一覧")
        notebook.add(usb_frame, text="USB一覧")
        notebook.add(timeline_outer, text="タイムライン")
        notebook.add(charts_frame, text="グラフ")
        notebook.add(correlation_frame, text="相関")
        notebook.add(event_frame, text="イベントログ")

        self._write_overview()

    def _build_charts_tab(self, parent: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=4)
        self.chart_ping = LineChart(frame, title="Ping 応答時間", unit="ms", line_color="#89b4fa")
        self.chart_net_sent = LineChart(frame, title="送信スループット", unit="Kbps", line_color="#a6e3a1")
        self.chart_net_recv = LineChart(frame, title="受信スループット", unit="Kbps", line_color="#94e2d5")
        self.chart_cpu = LineChart(frame, title="CPU 使用率", unit="%", line_color="#fab387", warn_above=90)
        self.chart_memory = LineChart(
            frame, title="メモリ 使用率", unit="%", line_color="#f9e2af", warn_above=90
        )
        self.chart_gpu = LineChart(frame, title="GPU 使用率", unit="%", line_color="#cba6f7", warn_above=90)

        charts = [
            self.chart_ping,
            self.chart_net_sent,
            self.chart_net_recv,
            self.chart_cpu,
            self.chart_memory,
            self.chart_gpu,
        ]
        for idx, chart in enumerate(charts):
            chart.grid(row=idx // 2, column=idx % 2, sticky="nsew", padx=4, pady=4)

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        for r in range(3):
            frame.rowconfigure(r, weight=1)
        return frame

    def _build_correlation_tab(self, parent: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=8)
        help_text = (
            "直近の警告・エラーイベントを起点に、前後10秒以内の関連イベントをまとめて表示します。\n"
            "コードリーダー停止時は、QRログの遮断 → イベントログ → COM Status変化 の順序を確認してください。"
        )
        ttk.Label(frame, text=help_text, wraplength=900).pack(anchor=tk.W, pady=(0, 8))
        self.correlation_text = tk.Text(frame, wrap=tk.WORD, height=24, state=tk.DISABLED)
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.correlation_text.yview)
        self.correlation_text.configure(yscrollcommand=scroll.set)
        self.correlation_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Button(frame, text="相関を再分析", command=self._refresh_correlation_panel).pack(
            anchor=tk.W, pady=(8, 0)
        )
        return frame

    def _make_tree(
        self, parent: tk.Misc, columns: tuple[str, ...]
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
        qr_cfg = self.config_data.get("qr_log", {})
        mon_cfg = self.config_data.get("monitoring", {})
        qr_dir = qr_cfg.get("directory") or "（未設定）"
        ping_target = mon_cfg.get("ping_target", "8.8.8.8")
        lines = [
            "PC Insight Monitor α v1.1",
            "",
            "この版でできること:",
            "  - COMポート / USBデバイスの状態監視",
            "  - Windowsイベントログ（System）のUSB関連イベント監視",
            "  - ネットワーク疎通・スループットの時系列グラフ",
            "  - CPU / メモリ / GPU 使用率の時系列グラフ",
            "  - 変化を1本のタイムラインへ表示（重要度色分け・フィルタ）",
            "  - 警告イベント前後の相関分析",
            "  - QRツールのUSB接続CSVをタイムラインへ取込",
            "",
            "起動できない場合:",
            "  1. diagnose.bat を実行して環境を確認",
            "  2. 開発PCで setup_portable.bat を再実行",
            "  3. python フォルダごとファイルサーバへ再配置",
            "",
            f"QRログフォルダ: {qr_dir}",
            f"Ping先: {ping_target}（config.json の monitoring.ping_target で変更可）",
            "",
            "調査の進め方:",
            "  1. 現象再現前に「監視開始」",
            "  2. 「グラフ」タブでネットワーク・リソースの変化を確認",
            "  3. 「タイムライン」でイベント順序を確認",
            "  4. 「相関」タブでトリガーととどめの候補を確認",
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
        qr_cfg = self.config_data.get("qr_log", {})
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
        mon_cfg = self.config_data.get("monitoring", {})
        self.usb_watcher.start()
        self.event_watcher.start()
        if mon_cfg.get("enable_system_metrics", True):
            self.system_watcher.start()
        if mon_cfg.get("enable_network_metrics", True):
            self.network_watcher.start()
        self._monitoring = True
        self.stat_vars["status"].set("監視中")
        self.refresh_device_tables()

    def stop_monitoring(self) -> None:
        self.usb_watcher.stop()
        self.event_watcher.stop()
        self.system_watcher.stop()
        self.network_watcher.stop()
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

        sys_summary = self.system_watcher.summary()
        cpu = sys_summary.get("cpu_percent")
        mem = sys_summary.get("memory_percent")
        self.stat_vars["cpu"].set(f"{cpu:.0f}%" if cpu is not None else "-")
        self.stat_vars["memory"].set(f"{mem:.0f}%" if mem is not None else "-")

        net_summary = self.network_watcher.summary()
        ping = net_summary.get("ping_ms")
        if ping is None:
            self.stat_vars["ping"].set("-")
        elif ping < 0:
            self.stat_vars["ping"].set("NG")
        else:
            self.stat_vars["ping"].set(f"{ping:.0f}ms")

    def _schedule_ui_refresh(self) -> None:
        self._drain_event_queue()
        if self._monitoring:
            self.refresh_device_tables()
            self._refresh_charts()
        self.after(self.POLL_UI_MS, self._schedule_ui_refresh)

    def _refresh_charts(self) -> None:
        self.chart_ping.set_data(self.metrics.get_series("ping_ms"))
        self.chart_net_sent.set_data(self.metrics.get_series("net_sent_kbps"))
        self.chart_net_recv.set_data(self.metrics.get_series("net_recv_kbps"))
        self.chart_cpu.set_data(self.metrics.get_series("cpu_percent"))
        self.chart_memory.set_data(self.metrics.get_series("memory_percent"))
        self.chart_gpu.set_data(self.metrics.get_series("gpu_percent"))

    def _drain_event_queue(self) -> None:
        count = int(self.stat_vars["event_count"].get() or 0)
        updated = False
        while True:
            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                break
            count += 1
            updated = True
            self._all_events.append(event)
            if self._passes_timeline_filter(event):
                self._insert_timeline_row(event)
        if updated:
            self.stat_vars["event_count"].set(str(count))
            children = self.timeline_tree.get_children()
            if len(children) > self.MAX_TIMELINE_ROWS:
                for item in children[self.MAX_TIMELINE_ROWS :]:
                    self.timeline_tree.delete(item)

    def _passes_timeline_filter(self, event: MonitorEvent) -> bool:
        selected = self._timeline_filter.get()
        if selected == "すべて":
            return True
        return event.source == selected

    def _insert_timeline_row(self, event: MonitorEvent) -> None:
        tag = event.severity if event.severity in SEVERITY_TAGS else "info"
        self.timeline_tree.insert("", 0, values=event.to_row(), tags=(tag,))

    def _apply_timeline_filter(self) -> None:
        self.timeline_tree.delete(*self.timeline_tree.get_children())
        for event in reversed(self._all_events[-self.MAX_TIMELINE_ROWS :]):
            if self._passes_timeline_filter(event):
                self._insert_timeline_row(event)

    def _highlight_correlations(self) -> None:
        self.timeline_tree.tag_configure("corr", background="#dbeafe")
        anchors = [
            e for e in self._all_events if e.severity in {"warning", "error"}
        ][-5:]
        if not anchors:
            messagebox.showinfo("相関ハイライト", "警告・エラーイベントがまだありません。")
            return

        window = timedelta(seconds=self.CORRELATION_WINDOW_SEC)
        highlight_times: set[str] = set()
        for anchor in anchors:
            for event in self._all_events:
                if abs(event.timestamp - anchor.timestamp) <= window:
                    highlight_times.add(event.timestamp.strftime("%Y-%m-%d %H:%M:%S"))

        for item in self.timeline_tree.get_children():
            values = self.timeline_tree.item(item, "values")
            if values and values[0] in highlight_times:
                tags = list(self.timeline_tree.item(item, "tags"))
                if "corr" not in tags:
                    tags.append("corr")
                self.timeline_tree.item(item, tags=tags)

        self._refresh_correlation_panel()

    def _refresh_correlation_panel(self) -> None:
        anchors = [e for e in self._all_events if e.severity in {"warning", "error"}]
        lines: list[str] = []
        if not anchors:
            lines.append("まだ警告・エラーイベントがありません。監視を開始して現象を再現してください。")
        else:
            window = timedelta(seconds=self.CORRELATION_WINDOW_SEC)
            for anchor in anchors[-8:]:
                lines.append(
                    f"■ 起点 [{anchor.timestamp:%H:%M:%S}] {anchor.source} / {anchor.category}"
                )
                lines.append(f"   {anchor.message}")
                related = [
                    e
                    for e in self._all_events
                    if e is not anchor and abs(e.timestamp - anchor.timestamp) <= window
                ]
                related.sort(key=lambda e: e.timestamp)
                if related:
                    for event in related:
                        lines.append(
                            f"   └ [{event.timestamp:%H:%M:%S}] {event.source}: {event.message}"
                        )
                else:
                    lines.append("   └ （前後10秒以内に関連イベントなし）")
                lines.append("")

        self.correlation_text.configure(state=tk.NORMAL)
        self.correlation_text.delete("1.0", tk.END)
        self.correlation_text.insert(tk.END, "\n".join(lines))
        self.correlation_text.configure(state=tk.DISABLED)

    def _on_close(self) -> None:
        self.stop_monitoring()
        self.destroy()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
