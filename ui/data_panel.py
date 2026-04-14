"""Data panel: real-time analog/digital data display."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
import time
from typing import Optional
from protocol.frames import DataFrame, ConfigFrame
from utils.time_utils import soc_to_beijing, fracsec_to_ms


class DataPanel(ttk.Frame):
    """Tab showing real-time data from substations."""

    def __init__(self, parent):
        super().__init__(parent)
        self._cfg: Optional[ConfigFrame] = None
        self._last_refresh = 0.0
        self._pending_frame: Optional[DataFrame] = None
        self._build()

    def _build(self):
        # Data table
        self.tree = ttk.Treeview(self, show="headings", height=20)
        vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Default columns
        self._setup_columns(["\u65f6\u95f4\u6233", "STAT"])

    def _setup_columns(self, columns: list[str]):
        self.tree["columns"] = columns
        for col in columns:
            self.tree.heading(col, text=col)
            width = 150 if col == "\u65f6\u95f4\u6233" else 80
            self.tree.column(col, width=width, minwidth=50)

    def set_config(self, cfg: ConfigFrame):
        """Update column headers based on config frame."""
        self._cfg = cfg
        cols = ["\u65f6\u95f4\u6233"]
        for i in range(cfg.annmr):
            idx = cfg.phnmr + i
            name = cfg.channel_names[idx] if idx < len(cfg.channel_names) else f"AN{i+1}"
            cols.append(name)
        cols.append("\u5f00\u5173\u91cf")
        cols.append("STAT")
        self._setup_columns(cols)

    def add_data(self, frame: Optional[DataFrame]):
        """Add a data frame (throttled to 200ms refresh)."""
        if not frame:
            return
        self._pending_frame = frame
        now = time.time()
        if now - self._last_refresh >= 0.2:
            self._flush()
            self._last_refresh = now

    def _flush(self):
        if not self._pending_frame:
            return
        frame = self._pending_frame
        self._pending_frame = None

        meas_rate = self._cfg.meas_rate if self._cfg else 1000000
        ms = fracsec_to_ms(frame.fracsec, meas_rate, frame.version)
        timestamp = f"{soc_to_beijing(frame.soc)}.{int(ms):03d}"

        values = [timestamp]
        if self._cfg:
            for i, raw in enumerate(frame.analog):
                factor = self._cfg.analog_factor(i)
                values.append(f"{raw * factor:.4f}")
        else:
            for raw in frame.analog:
                values.append(str(raw))

        # Digital as binary string
        digital_str = " ".join(f"{d:016b}" for d in frame.digital)
        values.append(digital_str)
        values.append(f"0x{frame.stat:04X}")

        self.tree.insert("", 0, values=values)
        # Keep max 500 rows
        children = self.tree.get_children()
        if len(children) > 500:
            for child in children[500:]:
                self.tree.delete(child)

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self._cfg = None
        self._pending_frame = None
