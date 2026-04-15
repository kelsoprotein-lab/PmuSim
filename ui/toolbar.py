"""Toolbar: start/stop server, protocol selector, port config."""
import tkinter as tk
from tkinter import ttk


class Toolbar(ttk.Frame):
    """Top toolbar with server controls and protocol/port configuration."""

    def __init__(self, parent, on_start, on_stop):
        super().__init__(parent)
        self._on_start = on_start
        self._on_stop = on_stop

        # Start/Stop buttons
        self.start_btn = ttk.Button(self, text="\u25b6 \u542f\u52a8", command=self._start)
        self.start_btn.pack(side=tk.LEFT, padx=(5, 2))
        self.stop_btn = ttk.Button(self, text="\u25a0 \u505c\u6b62", command=self._stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=2)

        ttk.Separator(self, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # Protocol selector
        ttk.Label(self, text="\u534f\u8bae:").pack(side=tk.LEFT, padx=(5, 2))
        self.protocol_var = tk.StringVar(value="V3")
        proto_combo = ttk.Combobox(self, textvariable=self.protocol_var,
                                    values=["V2", "V3"], width=4, state="readonly")
        proto_combo.pack(side=tk.LEFT, padx=2)
        proto_combo.bind("<<ComboboxSelected>>", self._on_protocol_change)

        ttk.Separator(self, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # Port config (data pipe only — master listens for substation data connections)
        ttk.Label(self, text="\u6570\u636e\u7aef\u53e3:").pack(side=tk.LEFT, padx=(5, 2))
        self.data_port_var = tk.StringVar(value="8001")
        ttk.Entry(self, textvariable=self.data_port_var, width=6).pack(side=tk.LEFT, padx=2)

    def _on_protocol_change(self, _event=None):
        if self.protocol_var.get() == "V2":
            self.data_port_var.set("7001")
        else:
            self.data_port_var.set("8001")

    def _start(self):
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        try:
            data_port = int(self.data_port_var.get())
        except ValueError:
            data_port = 8001
        self._on_start(data_port)

    def _stop(self):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self._on_stop()
