"""Themed modal dialogs."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .theme import Palette, apply_theme, set_titlebar_dark


class TypedConfirmDialog(tk.Toplevel):
    """The confirm button stays disabled until the user types the exact phrase."""

    def __init__(self, parent: tk.Misc, palette: Palette, title: str, message: str, phrase: str,
                 danger: bool = True):
        super().__init__(parent)
        self.result = False
        self._phrase = phrase
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        apply_theme(self, palette)
        self.configure(bg=palette.surface)

        body = ttk.Frame(self, style="Card.TFrame", padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=title, style="Heading.Card.TLabel").pack(anchor="w")
        ttk.Label(body, text=message, style="Card.TLabel", wraplength=420, justify="left").pack(
            anchor="w", pady=(10, 14))
        self._var = tk.StringVar()
        self._entry = ttk.Entry(body, textvariable=self._var, width=30)
        self._entry.pack(fill="x")
        row = ttk.Frame(body, style="Card.TFrame")
        row.pack(fill="x", pady=(18, 0))
        self._ok = ttk.Button(row, text=f"Confirm {phrase}", style="Danger.TButton" if danger else "Primary.TButton",
                              command=self._confirm, state="disabled")
        self._ok.pack(side="right")
        ttk.Button(row, text="Cancel", command=self._cancel).pack(side="right", padx=(0, 8))

        self._var.trace_add("write", self._check)
        self.bind("<Return>", lambda e: self._confirm())
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_reqwidth()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        set_titlebar_dark(self, palette.name == "dark")
        self.grab_set()
        self._entry.focus_set()

    def _check(self, *_args) -> None:
        self._ok.configure(state="normal" if self._var.get() == self._phrase else "disabled")

    def _confirm(self) -> None:
        if self._var.get() == self._phrase:
            self.result = True
            self.destroy()

    def _cancel(self) -> None:
        self.result = False
        self.destroy()

    def show(self) -> bool:
        self.wait_window(self)
        return self.result
