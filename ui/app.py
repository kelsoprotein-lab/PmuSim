"""Main application window."""
from __future__ import annotations
import asyncio
import queue
import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

from network.master import MasterStation
from ui.toolbar import Toolbar
from ui.station_list import StationListPanel
from ui.config_panel import ConfigPanel
from ui.data_panel import DataPanel
from ui.log_panel import LogPanel


class App:
    """Main PmuSim application."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("PmuSim - PMU\u4e3b\u7ad9\u6a21\u62df\u5668")
        self.root.geometry("1100x700")
        self.root.minsize(900, 500)

        self.event_queue: queue.Queue = queue.Queue()
        self.master_station: Optional[MasterStation] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        self._build_ui()
        self._poll_events()

    def _build_ui(self):
        # Toolbar
        self.toolbar = Toolbar(self.root, on_start=self._start_server, on_stop=self._stop_server)
        self.toolbar.pack(fill=tk.X, padx=5, pady=5)

        # Main content: left panel + right notebook
        content = ttk.Frame(self.root)
        content.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        # Left: station list + action buttons
        self.station_panel = StationListPanel(content, on_action=self._on_station_action)
        self.station_panel.pack(side=tk.LEFT, fill=tk.Y)

        # Bind station selection to update config/data panels
        self.station_panel.listbox.bind("<<ListboxSelect>>", self._on_station_selected)

        # Right: notebook with tabs
        right_frame = ttk.Frame(content)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.config_panel = ConfigPanel(self.notebook)
        self.notebook.add(self.config_panel, text=" \u914d\u7f6e ")

        self.data_panel = DataPanel(self.notebook)
        self.notebook.add(self.data_panel, text=" \u5b9e\u65f6\u6570\u636e ")

        self.log_panel = LogPanel(self.notebook)
        self.notebook.add(self.log_panel, text=" \u901a\u4fe1\u65e5\u5fd7 ")

        # Status bar
        self.status_var = tk.StringVar(value="\u5c31\u7eea")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, padx=5, pady=(0, 5))

    def _start_server(self, mgmt_port: int, data_port: int):
        """Start the asyncio backend in a background thread."""
        self.master_station = MasterStation(
            event_queue=self.event_queue,
            mgmt_port=mgmt_port,
            data_port=data_port,
        )
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.status_var.set(f"\u670d\u52a1\u8fd0\u884c\u4e2d - \u7ba1\u7406:{mgmt_port} \u6570\u636e:{data_port}")

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self.master_station.start())
        self._loop.run_forever()

    def _stop_server(self):
        """Stop the asyncio backend."""
        if self._loop and self.master_station:
            asyncio.run_coroutine_threadsafe(self.master_station.stop(), self._loop)
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=3)
            self._loop = None
            self._thread = None
            self.master_station = None
        self.station_panel.clear()
        self.config_panel.clear()
        self.data_panel.clear()
        self.log_panel.clear()
        self.status_var.set("\u5df2\u505c\u6b62")

    def _on_station_action(self, action: str, idcode: str, **kwargs):
        """Handle action button clicks from station list panel."""
        if not self.master_station or not self._loop:
            return

        if action == "request_cfg1":
            self.master_station.send_command("request_cfg1", idcode=idcode)
        elif action == "send_cfg2_cmd":
            self.master_station.send_command("send_cfg2_cmd", idcode=idcode)
        elif action == "send_cfg2":
            period = kwargs.get("period")
            self.master_station.send_command("send_cfg2", idcode=idcode, period=period)
        elif action == "request_cfg2":
            self.master_station.send_command("request_cfg2", idcode=idcode)
        elif action == "open_data":
            self.master_station.send_command("open_data", idcode=idcode)
        elif action == "close_data":
            self.master_station.send_command("close_data", idcode=idcode)
        elif action == "auto_handshake":
            period = kwargs.get("period")
            self.master_station.send_command("auto_handshake", idcode=idcode, period=period)

    def _on_station_selected(self, _event=None):
        """When user selects a station, update config and data panels."""
        idcode = self.station_panel.get_selected()
        if idcode and self.master_station:
            session = self.master_station.sessions.get(idcode)
            if session:
                # Show the latest config (prefer CFG-2 over CFG-1)
                cfg = session.cfg2 or session.cfg1
                self.config_panel.show_config(cfg)
                if cfg:
                    self.data_panel.set_config(cfg)

    def _poll_events(self):
        """Poll the event queue and update UI."""
        try:
            while True:
                event_type, kwargs = self.event_queue.get_nowait()
                self._handle_event(event_type, kwargs)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_events)

    def _handle_event(self, event_type: str, kwargs: dict):
        """Dispatch an event from the backend to the appropriate UI panel."""
        idcode = kwargs.get("idcode", "")

        if event_type == "session_created":
            self.station_panel.add_station(idcode, kwargs.get("peer_ip", ""))
            self._update_status()

        elif event_type == "session_disconnected":
            self.station_panel.update_station_state(idcode, "\u79bb\u7ebf")
            self._update_status()

        elif event_type in ("mgmt_connected", "data_connected"):
            self.station_panel.update_station_state(idcode, "\u5728\u7ebf")

        elif event_type == "cfg1_received":
            self.station_panel.update_station_state(idcode, "CFG1\u5df2\u63a5\u6536")
            cfg = kwargs.get("cfg")
            selected = self.station_panel.get_selected()
            if selected == idcode:
                self.config_panel.show_config(cfg)
                self.data_panel.set_config(cfg)

        elif event_type == "cfg2_sent":
            self.station_panel.update_station_state(idcode, "CFG2\u5df2\u4e0b\u53d1")

        elif event_type == "cfg2_received":
            cfg = kwargs.get("cfg")
            selected = self.station_panel.get_selected()
            if selected == idcode:
                self.config_panel.show_config(cfg)
                self.data_panel.set_config(cfg)

        elif event_type == "streaming_started":
            self.station_panel.update_station_state(idcode, "\u6570\u636e\u6d41")

        elif event_type == "streaming_stopped":
            self.station_panel.update_station_state(idcode, "CFG2\u5df2\u4e0b\u53d1")

        elif event_type == "data_frame":
            selected = self.station_panel.get_selected()
            if selected == idcode:
                self.data_panel.add_data(kwargs.get("frame"))

        elif event_type == "raw_frame":
            self.log_panel.add_log(
                idcode=idcode,
                direction=kwargs.get("direction", "?"),
                data=kwargs.get("data", b""),
            )

        elif event_type == "heartbeat_recv":
            pass  # Silent

        elif event_type == "heartbeat_timeout":
            self.station_panel.update_station_state(idcode, "\u5fc3\u8df3\u8d85\u65f6")

        elif event_type in ("error", "parse_error"):
            self.log_panel.add_error(idcode=idcode, error=kwargs.get("error", ""))

    def _update_status(self):
        if self.master_station:
            n = len(self.master_station.sessions)
            self.status_var.set(f"\u5df2\u8fde\u63a5\u5b50\u7ad9: {n}")

    def run(self):
        self.root.mainloop()
