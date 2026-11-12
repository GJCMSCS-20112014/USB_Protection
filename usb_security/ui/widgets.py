"""Reusable themed widgets. Anything that is not a ttk widget implements apply_theme(palette)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from ..config import LOG_MAX_LINES
from ..core.models import Change, ChangeType, DriveInfo
from ..core.utils import human_size
from .theme import MONO_FAMILY, Palette, font

_LABEL_STYLES = {"success": "Success.Card.TLabel", "warn": "Warn.Card.TLabel",
                 "danger": "Danger.Card.TLabel", "info": "Info.Card.TLabel",
                 "muted": "Muted.Card.TLabel"}


def scrolled(parent, factory: Callable[[tk.Misc], tk.Widget], horizontal: bool = False):
    """Wrap a widget with scrollbars. Returns (container, widget)."""
    box = ttk.Frame(parent, style="Card.TFrame")
    widget = factory(box)
    vbar = ttk.Scrollbar(box, orient="vertical", command=widget.yview)
    widget.configure(yscrollcommand=vbar.set)
    widget.grid(row=0, column=0, sticky="nsew")
    vbar.grid(row=0, column=1, sticky="ns")
    if horizontal:
        hbar = ttk.Scrollbar(box, orient="horizontal", command=widget.xview)
        widget.configure(xscrollcommand=hbar.set)
        hbar.grid(row=1, column=0, sticky="ew")
    box.rowconfigure(0, weight=1)
    box.columnconfigure(0, weight=1)
    return box, widget


class Card(tk.Frame):
    """Bordered surface with an optional title row and an action button on the right."""

    def __init__(self, parent, palette: Palette, title: str = "",
                 action_text: str = "", action: Optional[Callable[[], None]] = None):
        super().__init__(parent, bd=0, highlightthickness=1)
        self.action_button: Optional[ttk.Button] = None
        if title:
            head = ttk.Frame(self, style="Card.TFrame", padding=(18, 14, 18, 0))
            head.pack(fill="x")
            ttk.Label(head, text=title, style="Heading.Card.TLabel").pack(side="left")
            if action_text:
                self.action_button = ttk.Button(head, text=action_text, style="Small.TButton", command=action)
                self.action_button.pack(side="right")
        self.body = ttk.Frame(self, style="Card.TFrame", padding=(18, 12, 18, 16))
        self.body.pack(fill="both", expand=True)
        self.apply_theme(palette)

    def apply_theme(self, p: Palette) -> None:
        self.configure(bg=p.surface, highlightbackground=p.border, highlightcolor=p.border)


class Badge(tk.Label):
    def __init__(self, parent, palette: Palette, text: str = "", kind: str = "info"):
        super().__init__(parent, text=text, font=font(9, "bold"), padx=10, pady=3, bd=0)
        self._kind = kind
        self.apply_theme(palette)

    def set(self, text: str, kind: str) -> None:
        self._kind = kind
        self.configure(text=text)
        self.apply_theme(self._palette)

    def apply_theme(self, p: Palette) -> None:
        self._palette = p
        self.configure(bg=p.tint(self._kind), fg=p.fg(self._kind))


class KeyValueList(ttk.Frame):
    """Label/value rows. `set(key, text, kind)` colours the value (success/warn/danger/info/muted)."""

    def __init__(self, parent, rows: Sequence[Tuple[str, str]]):
        super().__init__(parent, style="Card.TFrame")
        self._values: Dict[str, ttk.Label] = {}
        self.columnconfigure(1, weight=1)
        for row, (key, caption) in enumerate(rows):
            ttk.Label(self, text=caption, style="Muted.Card.TLabel").grid(row=row, column=0, sticky="nw", pady=3)
            value = ttk.Label(self, text="\u2014", style="Card.TLabel", wraplength=250, justify="left")
            value.grid(row=row, column=1, sticky="nw", padx=(16, 0), pady=3)
            self._values[key] = value

    def set(self, key: str, text: str, kind: str = "") -> None:
        self._values[key].configure(text=text, style=_LABEL_STYLES.get(kind, "Card.TLabel"))

    def clear(self) -> None:
        for key in self._values:
            self.set(key, "\u2014")


class StatTile(tk.Frame):
    def __init__(self, parent, palette: Palette, caption: str):
        super().__init__(parent, bd=0, highlightthickness=1)
        self._kind = ""
        self._value = tk.Label(self, text="\u2014", font=font(20, "bold"), anchor="w")
        self._caption = tk.Label(self, text=caption.upper(), font=font(8, "bold"), anchor="w")
        self._value.pack(fill="x", padx=14, pady=(10, 0))
        self._caption.pack(fill="x", padx=14, pady=(0, 10))
        self.apply_theme(palette)

    def set(self, value, kind: str = "") -> None:
        self._kind = kind
        self._value.configure(text=f"{value:,}" if isinstance(value, int) else str(value))
        self.apply_theme(self._p)

    def apply_theme(self, p: Palette) -> None:
        self._p = p
        self.configure(bg=p.surface_alt, highlightbackground=p.border, highlightcolor=p.border)
        self._value.configure(bg=p.surface_alt, fg=p.fg(self._kind) if self._kind else p.text)
        self._caption.configure(bg=p.surface_alt, fg=p.muted)


class Banner(tk.Frame):
    """Big status strip: idle / info / success / warn / danger."""

    def __init__(self, parent, palette: Palette):
        super().__init__(parent, bd=0, highlightthickness=1)
        self._kind = "idle"
        self._stripe = tk.Frame(self, width=5, bd=0)
        self._stripe.pack(side="left", fill="y")
        inner = tk.Frame(self, bd=0)
        inner.pack(side="left", fill="both", expand=True, padx=16, pady=12)
        self._inner = inner
        self._title = tk.Label(inner, text="", font=font(13, "bold"), anchor="w", justify="left")
        self._detail = tk.Label(inner, text="", font=font(10), anchor="w", justify="left", wraplength=640)
        self._title.pack(fill="x")
        self._detail.pack(fill="x")
        inner.bind("<Configure>", lambda e: self._detail.configure(wraplength=max(200, e.width - 8)))
        self.apply_theme(palette)

    def set(self, kind: str, title: str, detail: str = "") -> None:
        self._kind = kind
        self._title.configure(text=title)
        self._detail.configure(text=detail)
        self.apply_theme(self._p)

    def apply_theme(self, p: Palette) -> None:
        self._p = p
        bg = p.tint(self._kind) if self._kind != "idle" else p.surface_alt
        accent = p.fg(self._kind) if self._kind != "idle" else p.border
        self.configure(bg=bg, highlightbackground=p.border, highlightcolor=p.border)
        self._stripe.configure(bg=accent)
        self._inner.configure(bg=bg)
        self._title.configure(bg=bg, fg=accent if self._kind != "idle" else p.text)
        self._detail.configure(bg=bg, fg=p.muted if self._kind == "idle" else p.text)


class ActionTile(tk.Frame):
    """Clickable card with a coloured stripe: replaces a plain button with title + explanation."""

    def __init__(self, parent, palette: Palette, title: str, subtitle: str, kind: str,
                 command: Callable[[], None]):
        super().__init__(parent, bd=0, highlightthickness=1, cursor="hand2")
        self._kind, self._command = kind, command
        self._enabled, self._hover = True, False
        self._stripe = tk.Frame(self, width=5, bd=0)
        self._stripe.pack(side="left", fill="y")
        self._inner = tk.Frame(self, bd=0)
        self._inner.pack(side="left", fill="both", expand=True, padx=14, pady=12)
        self._title = tk.Label(self._inner, text=title, font=font(11, "bold"), anchor="w")
        self._sub = tk.Label(self._inner, text=subtitle, font=font(9), anchor="w", justify="left", wraplength=230)
        self._title.pack(fill="x")
        self._sub.pack(fill="x", pady=(2, 0))
        for widget in (self, self._stripe, self._inner, self._title, self._sub):
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
            widget.bind("<Button-1>", self._click)
        self.apply_theme(palette)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._paint()

    def _enter(self, _e=None):
        self._hover = True
        self._paint()

    def _leave(self, _e=None):
        self._hover = False
        self._paint()

    def _click(self, _e=None):
        if self._enabled:
            self._command()

    def apply_theme(self, p: Palette) -> None:
        self._p = p
        self._paint()

    def _paint(self) -> None:
        p = self._p
        bg = p.hover if (self._hover and self._enabled) else p.surface
        stripe = p.fg(self._kind) if self._enabled else p.border
        self.configure(bg=bg, highlightbackground=p.border, highlightcolor=p.border)
        self._stripe.configure(bg=stripe)
        self._inner.configure(bg=bg)
        self._title.configure(bg=bg, fg=p.text if self._enabled else p.muted)
        self._sub.configure(bg=bg, fg=p.muted)


class LogView(tk.Text):
    """Read-only coloured activity log with a line cap."""

    def __init__(self, parent, palette: Palette):
        super().__init__(parent, wrap="word", bd=0, highlightthickness=0, padx=14, pady=10,
                         font=(MONO_FAMILY, 10), state="disabled", cursor="arrow", spacing1=2)
        self.apply_theme(palette)

    def append(self, level: str, message: str, stamp: str) -> None:
        self.configure(state="normal")
        self.insert("end", f"{stamp}  ", "ts")
        self.insert("end", f"{level:<4}  ", f"lvl_{level}")
        self.insert("end", message + "\n", level if level in ("PASS", "FAIL", "WARN") else "INFO")
        lines = int(self.index("end-1c").split(".")[0])
        if lines > LOG_MAX_LINES:
            self.delete("1.0", f"{lines - LOG_MAX_LINES}.0")
        self.configure(state="disabled")
        self.see("end")

    def text_content(self) -> str:
        return self.get("1.0", "end-1c")

    def apply_theme(self, p: Palette) -> None:
        self.configure(bg=p.console_bg, fg=p.text, selectbackground=p.selection,
                       selectforeground=p.selection_text, inactiveselectbackground=p.selection)
        self.tag_configure("ts", foreground=p.muted)
        self.tag_configure("INFO", foreground=p.text)
        for level, kind in (("PASS", "success"), ("FAIL", "danger"), ("WARN", "warn"), ("INFO", "muted")):
            self.tag_configure(f"lvl_{level}", foreground=p.fg(kind), font=(MONO_FAMILY, 10, "bold"))
        self.tag_configure("PASS", foreground=p.success)
        self.tag_configure("FAIL", foreground=p.danger)
        self.tag_configure("WARN", foreground=p.warn)


class DriveTable(ttk.Treeview):
    COLUMNS = (("drive", "Drive", 62, "w"), ("label", "Label", 140, "w"),
               ("size", "Size", 82, "e"), ("bus", "Bus", 74, "w"))

    def __init__(self, parent, palette: Palette, on_select: Callable[[int], None]):
        super().__init__(parent, columns=[c[0] for c in self.COLUMNS], show="headings",
                         selectmode="browse", height=6)
        for key, caption, width, anchor in self.COLUMNS:
            self.heading(key, text=caption, anchor=anchor if anchor != "e" else "e")
            self.column(key, width=width, anchor=anchor, stretch=(key == "label"))
        self._on_select = on_select
        self._current: Optional[int] = None      # row selected programmatically / last chosen
        self.bind("<<TreeviewSelect>>", self._changed)
        self.apply_theme(palette)

    def load(self, drives: Iterable[DriveInfo], selected: Optional[DriveInfo]) -> None:
        self.delete(*self.get_children())
        self._current = None
        for index, d in enumerate(drives):
            tag = "system" if d.is_system else ("usb" if d.is_usb else "other")
            bus = "System" if d.is_system else d.bus_name
            self.insert("", "end", iid=str(index), tags=(tag,),
                        values=(d.display_root, d.label, human_size(d.total), bus))
            if selected is not None and d.key == selected.key:
                self._current = index
                self.selection_set(str(index))

    def _changed(self, _event=None) -> None:
        # selection_set() queues <<TreeviewSelect>> asynchronously, so a flag would be reset too
        # early. Instead ignore events that merely echo what load() selected (prevents loops).
        chosen = self.selection()
        if not chosen:
            return
        index = int(chosen[0])
        if index == self._current:
            return
        self._current = index
        self._on_select(index)

    def apply_theme(self, p: Palette) -> None:
        self.tag_configure("usb", foreground=p.text)
        self.tag_configure("other", foreground=p.muted)
        self.tag_configure("system", foreground=p.muted)


class ChangesTable(ttk.Treeview):
    COLUMNS = (("status", "Status", 100, "w", False), ("path", "File", 420, "w", True),
               ("old", "Previous size", 110, "e", False), ("new", "Current size", 110, "e", False))

    def __init__(self, parent, palette: Palette):
        super().__init__(parent, columns=[c[0] for c in self.COLUMNS], show="headings", selectmode="browse")
        for key, caption, width, anchor, stretch in self.COLUMNS:
            self.heading(key, text=caption, anchor=anchor)
            self.column(key, width=width, anchor=anchor, stretch=stretch)
        self.apply_theme(palette)

    def load(self, changes: Iterable[Change]) -> None:
        self.delete(*self.get_children())
        for c in changes:
            self.insert("", "end", tags=(c.kind.value,), values=(
                c.kind.value, c.path,
                "" if c.old_length is None else human_size(c.old_length),
                "" if c.new_length is None else human_size(c.new_length)))

    def apply_theme(self, p: Palette) -> None:
        self.tag_configure(ChangeType.ADDED.value, foreground=p.info)
        self.tag_configure(ChangeType.MODIFIED.value, foreground=p.warn)
        self.tag_configure(ChangeType.DELETED.value, foreground=p.danger)
