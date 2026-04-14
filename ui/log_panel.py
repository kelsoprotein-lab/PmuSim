"""Log panel: communication log with hex dump."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
import time
from protocol.constants import FrameType, ProtocolVersion, Cmd, CMD_NAMES, parse_sync


class LogPanel(ttk.Frame):
    """Tab showing communication log entries."""

    def __init__(self, parent):
        super().__init__(parent)
        self._max_entries = 1000
        self._build()

    def _build(self):
        # Hex detail at bottom (pack first so it stays at bottom)
        self.hex_text = tk.Text(self, height=4, state=tk.DISABLED, font=("Courier", 10))
        self.hex_text.pack(side=tk.BOTTOM, fill=tk.X, padx=2, pady=2)

        # Log tree with scrollbar
        tree_frame = ttk.Frame(self)
        tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        cols = ("\u65f6\u95f4", "\u5b50\u7ad9", "\u65b9\u5411", "\u5e27\u7c7b\u578b", "\u6458\u8981")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=20)
        for col in cols:
            self.tree.heading(col, text=col)
        self.tree.column("\u65f6\u95f4", width=100)
        self.tree.column("\u5b50\u7ad9", width=90)
        self.tree.column("\u65b9\u5411", width=40)
        self.tree.column("\u5e27\u7c7b\u578b", width=80)
        self.tree.column("\u6458\u8981", width=300)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self._raw_data: dict[str, bytes] = {}  # tree item id -> raw bytes

    def add_log(self, idcode: str, direction: str, data: bytes):
        """Add a communication log entry."""
        ts = time.strftime("%H:%M:%S")
        arrow = "\u2192" if direction == "send" else "\u2190"
        frame_type, summary = self._summarize(data)

        item_id = self.tree.insert("", 0, values=(ts, idcode, arrow, frame_type, summary))
        self._raw_data[item_id] = data

        # Trim old entries
        children = self.tree.get_children()
        if len(children) > self._max_entries:
            for child in children[self._max_entries:]:
                self._raw_data.pop(child, None)
                self.tree.delete(child)

    def add_error(self, idcode: str, error: str):
        ts = time.strftime("%H:%M:%S")
        self.tree.insert("", 0, values=(ts, idcode, "!", "\u9519\u8bef", error))

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self._raw_data.clear()
        self.hex_text.config(state=tk.NORMAL)
        self.hex_text.delete("1.0", tk.END)
        self.hex_text.config(state=tk.DISABLED)

    def _summarize(self, data: bytes) -> tuple[str, str]:
        """Extract frame type and human-readable summary from raw bytes."""
        if len(data) < 4:
            return ("?", data.hex())
        try:
            sync = int.from_bytes(data[0:2], "big")
            frame_type, version = parse_sync(sync)
        except ValueError:
            return ("?", data[:20].hex())

        type_names = {
            FrameType.DATA: "\u6570\u636e\u5e27",
            FrameType.CFG1: "CFG-1",
            FrameType.CFG2: "CFG-2",
            FrameType.COMMAND: "\u547d\u4ee4\u5e27",
        }
        type_str = f"{type_names.get(frame_type, '?')}(V{version})"

        summary = f"{len(data)}\u5b57\u8282"
        if frame_type == FrameType.COMMAND:
            # Extract CMD field
            if version == ProtocolVersion.V2:
                cmd = int.from_bytes(data[16:18], "big") if len(data) >= 18 else 0
            else:
                cmd = int.from_bytes(data[20:22], "big") if len(data) >= 22 else 0
            cmd_name = CMD_NAMES.get(cmd, f"0x{cmd:04X}")
            summary = cmd_name

        return type_str, summary

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if sel:
            raw = self._raw_data.get(sel[0], b"")
            hex_str = " ".join(f"{b:02X}" for b in raw)
            self.hex_text.config(state=tk.NORMAL)
            self.hex_text.delete("1.0", tk.END)
            self.hex_text.insert("1.0", hex_str)
            self.hex_text.config(state=tk.DISABLED)
