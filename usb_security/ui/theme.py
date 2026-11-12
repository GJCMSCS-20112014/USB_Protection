"""Fixed light colour palette and ttk styling."""
from __future__ import annotations

import ctypes
import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"


def font(size: int = 10, weight: str = "normal"):
    return (FONT_FAMILY, size, weight)


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    surface: str
    surface_alt: str
    hover: str
    border: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    accent_text: str
    success: str
    warn: str
    danger: str
    info: str
    selection: str
    selection_text: str
    success_bg: str
    warn_bg: str
    danger_bg: str
    info_bg: str
    console_bg: str

    def fg(self, kind: str) -> str:
        return {"success": self.success, "warn": self.warn, "danger": self.danger,
                "info": self.info, "accent": self.accent, "muted": self.muted}.get(kind, self.text)

    def tint(self, kind: str) -> str:
        return {"success": self.success_bg, "warn": self.warn_bg, "danger": self.danger_bg,
                "info": self.info_bg, "accent": self.info_bg}.get(kind, self.surface_alt)


LIGHT = Palette(
    name="light", bg="#f4f6f8", surface="#ffffff", surface_alt="#eef1f5", hover="#e3e8ee",
    border="#d5dce4", text="#1f2933", muted="#667788", accent="#2563eb", accent_hover="#1d4fd0",
    accent_text="#ffffff", success="#1a7f37", warn="#9a6700", danger="#cf222e", info="#0969da",
    selection="#dbe8ff", selection_text="#0b2a5b", success_bg="#e6f4ea", warn_bg="#fff4d6",
    danger_bg="#fde8ea", info_bg="#e6f0ff", console_bg="#fbfcfd")



def apply_theme(root: tk.Misc, p: Palette) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    if isinstance(root, (tk.Tk, tk.Toplevel)):
        root.configure(bg=p.bg)

    flat = dict(bordercolor=p.border, lightcolor=p.border, darkcolor=p.border)
    style.configure(".", background=p.bg, foreground=p.text, fieldbackground=p.surface_alt,
                    troughcolor=p.surface_alt, focuscolor=p.accent, font=font(10), **flat)

    # Frames and labels
    style.configure("TFrame", background=p.bg)
    style.configure("Card.TFrame", background=p.surface)
    style.configure("TLabel", background=p.bg, foreground=p.text)
    style.configure("Muted.TLabel", foreground=p.muted)
    style.configure("Title.TLabel", font=font(20, "bold"))
    style.configure("Card.TLabel", background=p.surface, foreground=p.text)
    style.configure("Muted.Card.TLabel", foreground=p.muted)
    style.configure("Title.Card.TLabel", font=font(15, "bold"))
    style.configure("Heading.Card.TLabel", font=font(11, "bold"))
    for kind in ("success", "warn", "danger", "info"):
        style.configure(f"{kind.title()}.Card.TLabel", foreground=p.fg(kind))

    # Buttons
    def button(name, bg, fg, hover, pressed):
        style.configure(name, background=bg, foreground=fg, padding=(14, 8), relief="flat",
                        borderwidth=1, focusthickness=0, font=font(10, "bold"),
                        bordercolor=bg, lightcolor=bg, darkcolor=bg)
        style.map(name, background=[("disabled", p.surface_alt), ("pressed", pressed), ("active", hover)],
                  foreground=[("disabled", p.muted)], bordercolor=[("focus", p.accent)])

    button("TButton", p.surface_alt, p.text, p.hover, p.border)
    button("Primary.TButton", p.accent, p.accent_text, p.accent_hover, p.accent_hover)
    button("Danger.TButton", p.danger, "#ffffff", p.danger, p.danger)
    button("Ghost.TButton", p.bg, p.muted, p.surface_alt, p.border)
    style.configure("Small.TButton", padding=(10, 4), font=font(9))

    # Inputs
    style.configure("TEntry", fieldbackground=p.surface_alt, foreground=p.text, insertcolor=p.text,
                    padding=7, **flat)

    # Tables
    style.configure("Treeview", background=p.surface, fieldbackground=p.surface, foreground=p.text,
                    rowheight=30, borderwidth=0, relief="flat", font=font(10))
    style.map("Treeview", background=[("selected", p.selection)], foreground=[("selected", p.selection_text)])
    style.configure("Treeview.Heading", background=p.surface_alt, foreground=p.muted, relief="flat",
                    padding=(10, 7), font=font(9, "bold"), borderwidth=0)
    style.map("Treeview.Heading", background=[("active", p.surface_alt)])
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    # Progress bars
    style.configure("Accent.Horizontal.TProgressbar", background=p.accent, troughcolor=p.surface_alt,
                    bordercolor=p.surface_alt, lightcolor=p.accent, darkcolor=p.accent, thickness=8)
    style.configure("Usage.Horizontal.TProgressbar", background=p.info, troughcolor=p.surface_alt,
                    bordercolor=p.surface_alt, lightcolor=p.info, darkcolor=p.info, thickness=6)

    # Notebook
    style.configure("TNotebook", background=p.surface, borderwidth=0, tabmargins=(0, 0, 0, 0), **flat)
    style.configure("TNotebook.Tab", background=p.surface, foreground=p.muted, padding=(16, 8),
                    borderwidth=0, font=font(10, "bold"))
    style.map("TNotebook.Tab", background=[("selected", p.surface)], foreground=[("selected", p.accent)])

    # Scrollbars
    for orient in ("Vertical", "Horizontal"):
        style.configure(f"{orient}.TScrollbar", background=p.border, troughcolor=p.surface,
                        bordercolor=p.surface, arrowcolor=p.muted, lightcolor=p.border,
                        darkcolor=p.border, relief="flat", gripcount=0)
        style.map(f"{orient}.TScrollbar", background=[("active", p.muted)])


def set_titlebar_dark(window: tk.Misc, dark: bool) -> None:
    """Match the Windows title bar to the theme (Windows 10 1809+/11). Silently ignored elsewhere."""
    if os.name != "nt":
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old id)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value),
                                                          ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass
