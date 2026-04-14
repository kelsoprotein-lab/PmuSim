"""Config panel: shows CFG-1/CFG-2 parsed content."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Optional
from protocol.frames import ConfigFrame


class ConfigPanel(ttk.Frame):
    """Tab showing configuration frame details."""

    def __init__(self, parent):
        super().__init__(parent)
        self._build()

    def _build(self):
        # Basic info
        info_frame = ttk.LabelFrame(self, text="\u57fa\u672c\u4fe1\u606f")
        info_frame.pack(fill=tk.X, padx=5, pady=5)

        self._info_labels = {}
        fields = [
            ("cfg_type", "\u914d\u7f6e\u7c7b\u578b"),
            ("version", "\u534f\u8bae\u7248\u672c"),
            ("stn", "\u7ad9\u540d"),
            ("idcode", "IDCODE"),
            ("format_flags", "FORMAT"),
            ("period_ms", "\u4f20\u9001\u5468\u671f"),
            ("meas_rate", "MEAS_RATE"),
        ]
        for i, (key, label) in enumerate(fields):
            ttk.Label(info_frame, text=f"{label}:").grid(row=i, column=0, sticky=tk.W, padx=5, pady=1)
            var = tk.StringVar(value="-")
            ttk.Label(info_frame, textvariable=var).grid(row=i, column=1, sticky=tk.W, padx=5, pady=1)
            self._info_labels[key] = var

        # Analog channels
        an_frame = ttk.LabelFrame(self, text="\u6a21\u62df\u91cf\u901a\u9053")
        an_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        cols = ("\u5e8f\u53f7", "\u540d\u79f0", "ANUNIT", "\u7cfb\u6570")
        self.an_tree = ttk.Treeview(an_frame, columns=cols, show="headings", height=8)
        for c in cols:
            self.an_tree.heading(c, text=c)
            self.an_tree.column(c, width=80)
        self.an_tree.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Digital channels
        dg_frame = ttk.LabelFrame(self, text="\u5f00\u5173\u91cf\u901a\u9053")
        dg_frame.pack(fill=tk.X, padx=5, pady=5)

        dg_cols = ("\u5e8f\u53f7", "\u540d\u79f0", "\u6709\u6548")
        self.dg_tree = ttk.Treeview(dg_frame, columns=dg_cols, show="headings", height=4)
        for c in dg_cols:
            self.dg_tree.heading(c, text=c)
            self.dg_tree.column(c, width=100)
        self.dg_tree.pack(fill=tk.X, padx=2, pady=2)

    def show_config(self, cfg: Optional[ConfigFrame]):
        if not cfg:
            self.clear()
            return

        self._info_labels["cfg_type"].set(f"CFG-{cfg.cfg_type}")
        self._info_labels["version"].set(f"V{cfg.version}")
        self._info_labels["stn"].set(cfg.stn)
        self._info_labels["idcode"].set(cfg.pmu_idcode)
        self._info_labels["format_flags"].set(f"0x{cfg.format_flags:04X}")
        self._info_labels["period_ms"].set(f"{cfg.period_ms:.1f} ms (PERIOD={cfg.period})")
        self._info_labels["meas_rate"].set(f"{cfg.meas_rate} \u5fae\u79d2")

        # Analog channels
        self.an_tree.delete(*self.an_tree.get_children())
        for i in range(cfg.annmr):
            name = cfg.channel_names[cfg.phnmr + i] if (cfg.phnmr + i) < len(cfg.channel_names) else "?"
            anunit_val = cfg.anunit[i] if i < len(cfg.anunit) else 0
            factor = cfg.analog_factor(i)
            self.an_tree.insert("", tk.END, values=(i + 1, name, anunit_val, f"{factor:.5f}"))

        # Digital channels
        self.dg_tree.delete(*self.dg_tree.get_children())
        ch_offset = cfg.phnmr + cfg.annmr
        for w in range(cfg.dgnmr):
            _, valid_mask = cfg.digunit[w] if w < len(cfg.digunit) else (0, 0)
            for bit in range(16):
                idx = ch_offset + w * 16 + bit
                name = cfg.channel_names[idx] if idx < len(cfg.channel_names) else ""
                is_valid = "\u2713" if (valid_mask >> bit) & 1 else ""
                if name and name.strip("\x00"):
                    self.dg_tree.insert("", tk.END, values=(w * 16 + bit + 1, name, is_valid))

    def clear(self):
        for var in self._info_labels.values():
            var.set("-")
        self.an_tree.delete(*self.an_tree.get_children())
        self.dg_tree.delete(*self.dg_tree.get_children())
