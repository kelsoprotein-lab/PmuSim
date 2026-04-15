"""Left panel: substation list and action buttons."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional


class StationListPanel(tk.Frame):
    """Shows connected substations and action buttons."""

    def __init__(self, parent, on_action):
        super().__init__(parent, width=220, bg='#e8e8e8')
        self.pack_propagate(False)
        self._on_action = on_action
        self._stations: dict[str, dict] = {}  # idcode -> {state, peer_ip}

        # Station list
        tk.Label(self, text="\u5b50\u7ad9\u5217\u8868", font=("", 10, "bold"),
                 bg='#e8e8e8', fg='#000000').pack(pady=(5, 2))
        self.listbox = tk.Listbox(self, width=25, height=12, exportselection=False)
        self.listbox.pack(fill=tk.X, padx=5, pady=2)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        # State label
        self.state_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.state_var, fg="gray", bg='#e8e8e8').pack(pady=2)

        # Connect substation
        conn_frame = ttk.LabelFrame(self, text="\u8fde\u63a5\u5b50\u7ad9")
        conn_frame.pack(fill=tk.X, padx=5, pady=5)

        ip_row = ttk.Frame(conn_frame)
        ip_row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(ip_row, text="IP:").pack(side=tk.LEFT)
        self.conn_ip_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(ip_row, textvariable=self.conn_ip_var, width=14).pack(side=tk.LEFT, padx=2)

        port_row = ttk.Frame(conn_frame)
        port_row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(port_row, text="\u7aef\u53e3:").pack(side=tk.LEFT)
        self.conn_port_var = tk.StringVar(value="8000")
        ttk.Entry(port_row, textvariable=self.conn_port_var, width=7).pack(side=tk.LEFT, padx=2)

        ttk.Button(conn_frame, text="\u8fde\u63a5",
                   command=self._do_connect).pack(fill=tk.X, padx=5, pady=2)

        # Action buttons
        btn_frame = ttk.LabelFrame(self, text="\u64cd\u4f5c")
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        actions = [
            ("\u53ec\u5524CFG-1", "request_cfg1"),
            ("\u4e0b\u4f20CFG-2\u547d\u4ee4", "send_cfg2_cmd"),
            ("\u4e0b\u4f20CFG-2", "send_cfg2"),
            ("\u53ec\u5524CFG-2", "request_cfg2"),
            ("\u5f00\u542f\u6570\u636e", "open_data"),
            ("\u5173\u95ed\u6570\u636e", "close_data"),
        ]
        for label, action in actions:
            btn = ttk.Button(btn_frame, text=label,
                             command=lambda a=action: self._do_action(a))
            btn.pack(fill=tk.X, padx=5, pady=1)

        ttk.Separator(btn_frame).pack(fill=tk.X, padx=5, pady=3)

        # PERIOD editor for CFG-2
        period_row = ttk.Frame(btn_frame)
        period_row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(period_row, text="PERIOD:").pack(side=tk.LEFT)
        self.period_var = tk.StringVar(value="")
        ttk.Entry(period_row, textvariable=self.period_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(period_row, text="(\u7a7a=\u6cbf\u7528CFG-1)").pack(side=tk.LEFT)

        ttk.Button(btn_frame, text="\u4e00\u952e\u63e1\u624b",
                   command=lambda: self._do_action("auto_handshake")).pack(fill=tk.X, padx=5, pady=1)

    def add_station(self, idcode: str, peer_ip: str):
        if idcode not in self._stations:
            self._stations[idcode] = {"state": "\u5728\u7ebf", "peer_ip": peer_ip}
            self._refresh_list()

    def update_station_state(self, idcode: str, state: str):
        if idcode in self._stations:
            self._stations[idcode]["state"] = state
            self._refresh_list()
            if self.get_selected() == idcode:
                self.state_var.set(f"\u72b6\u6001: {state}")

    def get_selected(self) -> Optional[str]:
        sel = self.listbox.curselection()
        if sel:
            text = self.listbox.get(sel[0])
            return text.split(" ")[0]
        return None

    def clear(self):
        self._stations.clear()
        self.listbox.delete(0, tk.END)
        self.state_var.set("")

    def _refresh_list(self):
        selected = self.get_selected()
        self.listbox.delete(0, tk.END)
        for idcode, info in self._stations.items():
            self.listbox.insert(tk.END, f"{idcode}  [{info['state']}]")
        # Re-select
        if selected:
            for i in range(self.listbox.size()):
                if self.listbox.get(i).startswith(selected):
                    self.listbox.selection_set(i)
                    break

    def _on_select(self, _event=None):
        idcode = self.get_selected()
        if idcode and idcode in self._stations:
            self.state_var.set(f"\u72b6\u6001: {self._stations[idcode]['state']}")

    def _do_connect(self):
        ip = self.conn_ip_var.get().strip()
        try:
            port = int(self.conn_port_var.get().strip())
        except ValueError:
            port = 8000
        self._on_action("connect", "", host=ip, port=port)

    def _do_action(self, action: str):
        idcode = self.get_selected()
        if idcode:
            period = None
            period_str = self.period_var.get().strip()
            if period_str:
                try:
                    period = int(period_str)
                except ValueError:
                    pass
            self._on_action(action, idcode, period=period)
